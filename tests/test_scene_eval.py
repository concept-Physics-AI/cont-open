import json

import pytest

from cont.dialogue import scene_eval as E
from cont.llm import LLMResponse

CFG = E.load_cases()


def st(i, tool, **a):
    return {"id": i, "tool": tool, "args": a}


# 사례별로 "올바르게 푼" 계획. 이 계획을 내는 가짜 공급자는 모든 사례를 통과해야 한다(측정기 자체의 검증).
ORACLE = {
    "정렬 단계만 절반 속도로 해줘": [st("a", "set_stage_speed", stage="align", factor=0.5)],
    "두 번째 단계를 0.5배로 느리게 해줘": [st("a", "set_stage_speed", stage="2", factor=0.5)],
    "카메라를 방위각 90도로 돌려줘": [st("a", "set_camera", azimuth=90)],
    "정렬 단계는 0.5배로 느리게 하고 카메라를 방위각 120도로 돌려서 보여줘": [st("a", "set_stage_speed", stage="2", factor=0.5), st("b", "set_camera", azimuth=120)],
    "재생 위치를 3초로 옮겨줘": [st("a", "seek", t=3)],
    "위 다이(실리콘)의 윗면 z1을 2.4로 올려줘": [st("a", "select_part", ref="die.si"), {"id": "b", "tool": "edit_part", "args": {"changes": {"z1": 2.4}}, "depends_on": ["a"]}],
    "접촉 단계 설명 이미지를 만들어줘": [st("a", "make_image", stage="contact")],
    "정렬 단계를 0.5배로 해줘": [st("a", "set_stage_speed", stage="align", factor=0.5)],
    "아니, 0.25배로 바꿔줘": [st("a", "set_stage_speed", stage="align", factor=0.25)],
    "위 다이(실리콘)를 선택해줘": [st("a", "select_part", ref="die.si")],
    "그 부품의 윗면 z1을 2.5로 올려줘": [st("a", "edit_part", changes={"z1": 2.5})],
    "유전층의 윗면 z1을 1.5로 해줘": [st("a", "select_part", ref="유전층"), {"id": "b", "tool": "edit_part", "args": {"changes": {"z1": 1.5}}, "depends_on": ["a"]}],
    "접합부 온도를 800K로 올려줘": [],
    "정렬 단계를 더 느리게 해줘": [],
    "정렬 단계를 0.5배로 하고 프로젝트를 저장해줘": [st("a", "set_stage_speed", stage="align", factor=0.5), {"id": "b", "tool": "save_project", "args": {}, "depends_on": ["a"]}],
}


class ByText:
    name = model = "oracle"

    def __init__(self, table):
        self.table = table

    def complete(self, messages, **opts):
        assert opts == {"temperature": 0}                              # 설정의 공급자 옵션이 전달된다
        return LLMResponse(json.dumps({"steps": self.table.get(messages[-1].content, [])}, ensure_ascii=False), "oracle", "oracle")


def test_every_case_text_has_an_oracle_plan():
    texts = {t for c in CFG["cases"] for t in c["turns"]}
    assert texts == set(ORACLE)


def test_oracle_provider_passes_every_case_and_the_report_is_complete():
    res = E.run(ByText(ORACLE), CFG, repeat=1)
    assert res["passed"] == res["trials"] == len(CFG["cases"]), [r for r in res["rows"] if not r["passed"]]
    assert res["provider"] == "oracle" and set(res["per_case"]) == {c["id"] for c in CFG["cases"]}
    assert set(res["turn_kinds"]) <= {"done", "refused", "failed"} and res["seconds"]["max"] >= res["seconds"]["median"]


def test_provider_that_never_plans_fails_every_case_that_expects_a_change():
    res = E.run(ByText({}), CFG, repeat=1)
    ok = {r["id"] for r in res["rows"] if r["passed"]}
    assert ok == {c["id"] for c in CFG["cases"] if c["expect"].get("unchanged")}


def test_wrong_but_valid_plans_are_caught_by_the_state_check():
    table = dict(ORACLE)
    table["정렬 단계만 절반 속도로 해줘"] = [st("a", "set_stage_speed", stage="approach", factor=0.5)]          # 다른 단계를 바꿈
    table["카메라를 방위각 90도로 돌려줘"] = [st("a", "set_camera", azimuth=90), st("b", "seek", t=1)]           # 요청에 없는 변경
    res = E.run(ByText(table), CFG, only=["speed_half_align", "camera_azimuth"], repeat=1)
    assert res["passed"] == 0
    f = {r["id"]: r["failures"] for r in res["rows"]}
    assert any("approach 속도" in x for x in f["speed_half_align"]) and any("재생 위치" in x for x in f["camera_azimuth"])


def test_bad_case_definition_is_refused(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("repeat: 1\ncases:\n  - id: x\n    turns: [a]\n    expect: {bogus: 1}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bogus"):
        E.load_cases(p)
