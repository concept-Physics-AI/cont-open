"""팩 출력 계약: 모든 물리 팩의 결과가 같은 칸을 갖춘다 (ARCHITECTURE.md "팩 출력 계약")."""
from dataclasses import asdict

import pytest

from cont import packs
from cont.answer import NOT_REPORTED
from cont.packs.diagnosis import synthetic as syn
from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate
from cont.service import api


def _fastening():
    steel = 205000.0
    j = BoltedJoint("M10", "10.9", Plate(15.0, steel, 700.0), Plate(15.0, steel, 700.0), outer_diameter=40.0)
    l = LoadCase(50.0, 0.12, 0.12, (0.10, 0.14), axial_load_max=6000.0, transverse_load=1500.0, friction_interface=0.15, embedding=0.008)
    return {"joint": asdict(j), "load": asdict(l)}


def _diagnosis():
    cur = syn.inject(syn.drive(2000, seed=2), "current", 1200, 1500, 0.9)
    return {"module": "drive", "normal": syn.drive(3000, seed=1), "current": cur,
            "signals": {"current": "current", "vibration": "vibration", "temperature": "temperature"},
            "conditions": {"load": "load", "speed": "speed"}, "time": "t"}


CASES = {
    "fastening": _fastening,
    "machining": lambda: {"cut": {"material": "C45", "diameter": 60.0, "cutting_speed": 180.0, "feed": 0.25, "depth": 2.0}},
    "heat": lambda: {"case": "sine_1d"},
    "heat_pinn": lambda: {"points": [[0.5, 0.5], [0.5, 2.0]], "profile": "smoke"},
    "diagnosis": _diagnosis,
}


def test_every_registered_pack_has_a_contract_case():
    assert set(packs.names()) == set(CASES), "새 팩은 CASES에 계약 시험용 입력을 더한다"


@pytest.mark.parametrize("name", sorted(CASES))
def test_pack_answers_meet_the_output_contract(name):
    body = api.solve(name, CASES[name]())
    a = body["answer"]
    assert a["quantities"], "예측값이 하나도 없다"
    for q in a["quantities"]:
        assert isinstance(q["unit"], str) and q["unit"].strip(), f"{q['key']}: 단위 칸이 비었다 (무차원은 '-')"
    assert a["inputs"], "다시 계산할 입력이 없다"
    assert a["status"] and a["method"] and a["basis"]
    assert a["provenance"]["producer"].startswith("pack:") and a["provenance"]["run_id"].startswith("run-")
    assert body["revision_id"].startswith("rev-") and body["content_hash"]
    trust = dict((k, v) for k, v in body["trust"])
    for key in ("불확실성", "적용 범위", "실패 조건", "물리잔차", "증거 수준", "검증 상태"):
        assert trust[key], f"{key} 칸이 비어 있다 (비면 '{NOT_REPORTED}'가 나와야 한다)"
    again = api.solve(name, CASES[name]())
    assert again["content_hash"] == body["content_hash"], "같은 입력인데 내용 해시가 다르다"
