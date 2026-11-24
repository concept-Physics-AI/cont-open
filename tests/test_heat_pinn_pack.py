"""서비스의 heat_pinn 팩: 문지기를 거쳐 PINN 또는 물리 선생 값을 낸다. torch가 없어도 답한다."""
import math

import pytest

from cont import packs
from cont.learn import pack as learned
from cont.service import api


def test_pack_is_registered_and_listed_with_limits():
    assert "heat_pinn" in packs.names()
    row = next(p for p in api.list_packs() if p["key"] == "heat_pinn")
    assert "문지기" in row["name"] and "처음 부를 때" in row["limits"]


def test_without_torch_every_point_is_answered_by_the_teacher(monkeypatch):
    monkeypatch.setattr(learned, "available", lambda: False)
    r = api.solve("heat_pinn", {"points": [[0.5, 0.5], [0.5, 2.0], [1.5, 0.5]]})
    q = {x["key"]: x for x in r["answer"]["quantities"]}
    assert q["u_0"]["value"] == pytest.approx(math.exp(-0.1 * math.pi ** 2 * 0.5), abs=2e-4)
    assert q["u_1"]["value"] == pytest.approx(math.exp(-0.1 * math.pi ** 2 * 2.0), abs=2e-4)
    assert q["u_2"]["value"] is None and not [k for k in q if k.startswith("deviation")]
    assert r["answer"]["method"].startswith("유한차분") and "PINN 모형이 없다" in " ".join(r["answer"]["basis"])
    assert "증거 수준 E1" in r["truth_line"]


def test_with_torch_inside_range_uses_pinn_and_reports_deviation():
    pytest.importorskip("torch")
    r = api.solve("heat_pinn", {"points": [[0.5, 0.5], [0.5, 2.0]], "profile": "smoke"})
    keys = {x["key"] for x in r["answer"]["quantities"]}
    assert {"u_0", "deviation_0", "u_1"} <= keys and "deviation_1" not in keys
    assert "증거 수준 E0" in r["truth_line"] and "PINN" in r["answer"]["method"]


def test_input_is_checked():
    for bad in ({}, {"points": []}, {"points": "x"}, {"points": [[0.5]]}, {"points": [["a", 1]]}, {"points": [[0.5, 1]] * 21},
                {"points": [[0.5, 0.5]], "alpha": "b"}, {"points": [[0.5, -1]]}):
        with pytest.raises(ValueError):
            api.solve("heat_pinn", bad)
