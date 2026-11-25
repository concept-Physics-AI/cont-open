"""개념별 책임 모듈 점검 (config/authority.yaml)."""
import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TABLE = yaml.safe_load((ROOT / "config" / "authority.yaml").read_text(encoding="utf-8"))


def _py_files():
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def _allowed(b):
    a = b["allowed_in"]
    return [a] if isinstance(a, str) else list(a)


def _rel(p):
    return p.relative_to(ROOT).as_posix()


def test_owners_exist():
    for c in TABLE["concepts"]:
        assert (ROOT / c["owner"]).is_file(), f"{c['key']}: {c['owner']}가 없습니다"
    for b in TABLE["sdk_boundaries"]:
        for d in _allowed(b):
            assert (ROOT / d).is_dir(), f"{b['key']}: {d}가 없습니다"


def test_owner_defines_its_symbols():
    for c in TABLE["concepts"]:
        tree = ast.parse((ROOT / c["owner"]).read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        assert set(c["defines"]) <= names, f"{c['key']}: 책임 모듈에 {set(c['defines']) - names}이(가) 없습니다"


def test_symbols_defined_only_in_owner():
    for c in TABLE["concepts"]:
        for p in _py_files():
            if _rel(p) == c["owner"]:
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"))
            dup = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name in c["defines"]]
            assert not dup, f"{_rel(p)}에서 {dup}을(를) 다시 정의했습니다. 책임 모듈은 {c['owner']}입니다"


def _imported(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module)
    return out


def test_sdk_calls_only_inside_allowed_dir():
    for b in TABLE["sdk_boundaries"]:
        allowed = [ROOT / d for d in _allowed(b)]
        banned = tuple(b["modules"])
        for p in _py_files():
            if any(a in p.parents for a in allowed):
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"))
            bad = [m for m in _imported(tree) if any(m == x or m.startswith(x + ".") for x in banned)]
            assert not bad, f"{_rel(p)}가 {bad}을(를) 직접 불러옵니다. {_allowed(b)} 안에서만 허용됩니다"


def test_checker_catches_violation(tmp_path):
    tree = ast.parse("import anthropic\nfrom openai import OpenAI\nclass PhysicsAnswer: pass\n")
    assert {"anthropic", "openai"} <= _imported(tree)
    assert any(isinstance(n, ast.ClassDef) and n.name == "PhysicsAnswer" for n in ast.walk(tree))
