"""학습 뼈대 시험. torch가 없으면 건너뛴다 (CI의 학습 작업은 CONT_REQUIRE_TORCH=1로 건너뛰기를 실패로 만든다)."""
import ast
import os
from pathlib import Path

import pytest

from cont import learn
from cont.learn import TrainConfig, TrainingRecord, load_profile

SRC = Path(__file__).resolve().parents[2] / "src"


def test_config_loads_without_torch_and_rejects_bad_values():
    c = load_profile("default")
    assert c.hidden == (32, 32, 32) and c.dtype == "float64"
    assert TrainConfig.from_dict(c.to_dict()) == c
    for bad in ({"activation": "relu"}, {"epochs": 0}, {"hidden": ()}, {"weights": {"pde": 1.0}}, {"dtype": "float16"}):
        with pytest.raises(ValueError):
            TrainConfig.from_dict({**c.to_dict(), **bad})
    with pytest.raises(KeyError):
        load_profile("nope")


def test_record_fingerprint_ignores_environment_only():
    c = load_profile("smoke")
    a = TrainingRecord("p", c, (1.0, 0.5), 1, {"pde": 0.1}, torch_version="2.15.0")
    b = TrainingRecord("p", c, (1.0, 0.5), 1, {"pde": 0.1}, torch_version="2.16.0")
    d = TrainingRecord("p", c, (1.0, 0.6), 1, {"pde": 0.1}, torch_version="2.15.0")
    assert a.fingerprint() == b.fingerprint() != d.fingerprint()


def test_torch_is_imported_only_inside_learn():
    """torch 가져오기는 cont.learn 안에서만 (config/authority.yaml의 학습 경계)."""
    for p in SRC.rglob("*.py"):
        if "learn" in p.relative_to(SRC).parts:
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""] if isinstance(n, ast.ImportFrom) else []
            assert not any(x.split(".")[0] == "torch" for x in names), f"{p}에서 torch를 가져옵니다"


def test_require_torch_message_when_missing(monkeypatch):
    monkeypatch.setattr(learn, "available", lambda: False)
    with pytest.raises(RuntimeError, match=r"\[learn\]"):
        learn.require_torch()


def test_ci_learning_job_has_torch():
    if os.environ.get("CONT_REQUIRE_TORCH") == "1":
        assert learn.available(), "학습 작업에서는 torch가 있어야 합니다"


def test_mlp_is_deterministic_for_same_seed_and_differs_across_seeds():
    torch = pytest.importorskip("torch")
    from cont.learn.net import build_mlp, count_parameters
    c = load_profile("smoke")
    x = torch.linspace(0, 1, 7, dtype=torch.float64).reshape(-1, 1)
    a, b = build_mlp(1, c)(x), build_mlp(1, c)(x)
    other = build_mlp(1, TrainConfig.from_dict({**c.to_dict(), "seed": 1}))(x)
    assert torch.equal(a, b) and not torch.equal(a, other)
    assert count_parameters(build_mlp(2, c)) == (2 * 16 + 16) + (16 * 16 + 16) + (16 + 1)
    assert a.dtype == torch.float64
