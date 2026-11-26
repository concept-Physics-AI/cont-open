import json

import pytest

import cont.generation.providers as gen_providers
from cont.dialogue.plan import PlanError, Plan, Step, Tool, validate
from cont.dialogue.scene_chat import SceneSession, diff_lines
from cont.generation import get_generator
from cont.llm import LLMResponse
from cont.objspec import ViewState, hybrid_bonding_stack
from cont.service.project import open_project

S = hybrid_bonding_stack()


class Canned:
    name = model = "canned"

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def complete(self, messages, **opts):
        self.seen.append(messages)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return LLMResponse(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False), "canned", "canned")


def step(i, tool, **args):
    return {"id": i, "tool": tool, "args": args}


def plan(*steps):
    return {"steps": list(steps)}


def session(tmp_path, *replies, spec=S, **kw):
    return SceneSession(spec, get_generator("fake"), Canned(*replies), root=tmp_path / "proj", project_id="p1", name="본딩", **kw)


def test_first_acceptance_turns_slow_stage_rotate_compare_and_save(tmp_path):
    p = plan(step("a", "set_stage_speed", stage="2", factor=0.5), step("b", "set_camera", azimuth=120, elevation=30),
             step("c", "compare"), step("d", "save_project"))
    ss = session(tmp_path, p)
    t = ss.turn("두 번째 단계만 느리게 하고 회전해서 보여줘. 이전 것과 비교하고 저장해줘")
    assert t.kind == "done" and [s["state"] for s in t.steps] == ["done"] * 4
    assert "정렬 단계 재생 속도 0.5배" in t.reply and "6.0s → 8.0s" in t.reply and "카메라 azimuth 120.0" in t.reply
    assert "정렬 단계 속도 1.0배→0.5배" in t.reply and "개정 1" in t.reply
    assert ss.view.speed_of("align") == 0.5 and ss.view.speed_of("approach") == 1.0 and ss.spec == S      # 구조는 그대로
    o = open_project(tmp_path / "proj")
    assert o.state.view == ss.view and o.state.spec.version == S.version


def test_plan_prompt_carries_state_tools_and_history(tmp_path):
    ss = session(tmp_path, plan(step("a", "seek", t=1)), plan(step("a", "seek", t=2)))
    ss.turn("1초로")
    ss.turn("2초로")
    msgs = ss.provider.seen[1]
    text = "\n".join(m.content for m in msgs)
    assert '"id": "die.si"' in text and "set_stage_speed(stage:str, factor:int/float)" in text and '"playback_t": 1.0' in text
    assert any(m.role == "user" and m.content == "1초로" for m in msgs)                              # 이전 왕복이 문맥에 들어간다
    assert msgs[-1].content == "2초로"


def test_failed_step_rolls_back_the_whole_request(tmp_path):
    p = plan(step("a", "set_camera", azimuth=200), step("b", "set_stage_speed", stage="9", factor=2.0))
    ss = session(tmp_path, p)
    before = (ss.spec, ss.view, ss.selection, ss.playback_t)
    t = ss.turn("카메라 돌리고 아홉 번째 단계 빠르게")
    assert t.kind == "failed" and "되돌렸습니다" in t.reply and t.changes == []
    assert [s["state"] for s in t.steps] == ["done", "failed"]
    assert (ss.spec, ss.view, ss.selection, ss.playback_t) == before


def test_ambiguous_reference_fails_and_names_candidates(tmp_path):
    p = plan(step("a", "select_part", ref="유전층"))
    ss = session(tmp_path, p)
    t = ss.turn("유전층 골라줘")
    assert t.kind == "failed" and ss.selection == () and "여러 부품에 해당합니다" in t.reply and "wafer.dielectric" in t.reply and "die.dielectric" in t.reply


def test_select_then_edit_changes_only_that_part(tmp_path):
    p = plan(step("a", "select_part", ref="위 다이"), {"id": "b", "tool": "edit_part", "args": {"changes": {"z1": 2.4}}, "depends_on": ["a"]})
    ss = session(tmp_path, p)
    t = ss.turn("위 다이 두께를 키워줘")
    assert t.kind == "done" and ss.selection == ("die.si",) and "z1 2.0→2.4" in t.reply
    assert ss.spec.part("die.si").part.z1 == 2.4 and ss.spec.part("wafer.si") == S.part("wafer.si")
    assert diff_lines(S, ViewState(), ss.spec, ss.view) == ["위 다이(실리콘): z1 2.0→2.4"]


def test_edit_without_selection_or_same_value_fails_and_changes_nothing(tmp_path):
    ss = session(tmp_path, plan(step("a", "edit_part", changes={"z1": 2.4})), plan(step("a", "select_part", ref="die.si"), step("b", "edit_part", changes={"z1": 2.0})))
    assert ss.turn("키워줘").kind == "failed" and ss.spec == S
    t = ss.turn("같은 값으로")
    assert t.kind == "failed" and "바뀐 것이 없습니다" in t.reply and ss.selection == ()                  # 선택도 되돌림


def test_invalid_plans_are_refused_without_running_anything(tmp_path):
    cases = ["이건 JSON이 아닙니다", plan(step("a", "rm_rf", path="/")), plan(step("a", "set_camera", azimuth="돌려")),
             plan(step("a", "set_stage_speed", stage="2")), {"steps": "x"}, plan(step("a", "set_camera", bogus=1))]
    ss = session(tmp_path, *cases)
    for i in range(len(cases)):
        t = ss.turn(f"요청 {i}")
        assert t.kind == "refused" and "실행하지 않았습니다" in t.reply
    assert ss.view == ViewState() and ss.spec == S


def test_empty_plan_means_not_understood_and_no_provider_means_refusal(tmp_path):
    ss = session(tmp_path, {"steps": []})
    assert "풀지 못했습니다" in ss.turn("그냥 좋게 해줘").reply
    bare = SceneSession(S, get_generator("fake"), None)
    assert bare.turn("느리게").kind == "refused"
    broken = session(tmp_path, RuntimeError("연결 끊김"))
    t = broken.turn("느리게")
    assert t.kind == "refused" and "공급자 호출에 실패" in t.reply


def test_fake_image_is_reported_as_not_real_and_saved_with_the_project(tmp_path):
    ss = session(tmp_path, plan(step("a", "make_image", stage="접촉"), step("b", "save_project")))
    t = ss.turn("접촉 단계 그림을 만들고 저장해줘")
    assert "가짜 생성기, 실제 생성 아님" in t.reply and t.kind == "done"
    o = open_project(tmp_path / "proj")
    assert len(o.state.images) == 1 and o.state.images[0].record["real"] is False and o.state.images[0].stage == "contact"


def test_failed_turn_discards_new_images_too(tmp_path):
    ss = session(tmp_path, plan(step("a", "make_image"), step("b", "seek", t=99)))
    t = ss.turn("그림 만들고 99초로")
    assert t.kind == "failed" and ss.new_images == []


def test_reopen_restores_state_without_calling_the_generator_or_provider(tmp_path, monkeypatch):
    ss = session(tmp_path, plan(step("a", "set_stage_speed", stage="align", factor=2), step("b", "select_part", ref="die"),
                                step("c", "seek", t=1.5), step("d", "make_image", stage="1"), step("e", "save_project")))
    assert ss.turn("정렬 빠르게, 다이 선택, 1.5초, 그림, 저장").kind == "done"
    monkeypatch.setattr(gen_providers.Fake, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("모델 재호출")))
    re = SceneSession.open(tmp_path / "proj", get_generator("fake"), None)
    assert re.view == ss.view and re.selection == ss.selection == ("die.dielectric", "die.si") and re.playback_t == 1.5
    assert len(re.saved_images) == 1 and re.state_json()["last_image"]["stage"] == "approach"
    assert re.state_json()["selection"] == ["die.dielectric", "die.si"] and re.baseline[1] == re.view


def test_save_without_project_folder_fails_cleanly():
    ss = SceneSession(S, get_generator("fake"), Canned(plan(step("a", "set_camera", azimuth=10), step("b", "save_project"))))
    t = ss.turn("돌리고 저장")
    assert t.kind == "failed" and "프로젝트 폴더" in t.reply and ss.view == ViewState()


def test_same_plan_asked_again_runs_again(tmp_path):
    p = plan(step("a", "seek", t=1))
    ss = session(tmp_path, p, plan(step("a", "set_camera", azimuth=50)), p)
    ss.turn("1초로"); ss.turn("카메라"); ss.playback_t = 4.0
    ss.turn("1초로")
    assert ss.playback_t == 1.0                                                  # 실행기가 이전 결과를 재사용하지 않는다


def test_plan_validate_accepts_tuple_types_and_refuses_bool_for_numbers():
    tool = Tool("t", lambda x: {"x": x}, {"x": (int, float)})
    assert validate(Plan((Step("a", "t", {"x": 1}),)), {"t": tool}) == ["a"]
    assert validate(Plan((Step("a", "t", {"x": 0.5}),)), {"t": tool}) == ["a"]
    for bad in (True, "1"):
        with pytest.raises(PlanError, match="int/float"):
            validate(Plan((Step("a", "t", {"x": bad}),)), {"t": tool})


def test_prompt_field_names_match_editable_fields_and_say_undo_is_unsupported():
    from cont.dialogue.scene_chat import _EDITABLE, SYSTEM_PROMPT
    from cont.objspec.select import _FIELDS
    assert _EDITABLE == _FIELDS
    assert all(f in SYSTEM_PROMPT for f in _FIELDS)
    assert "되돌리기·취소는 지원하지 않는다" in SYSTEM_PROMPT


def test_first_json_object_is_used_when_text_follows_it(tmp_path):
    p = plan(step("s1", "set_camera", azimuth=90))
    text = json.dumps(p, ensure_ascii=False) + "\n설명: 카메라를 돌렸습니다 {참고}"
    s = session(tmp_path, text)
    t = s.turn("카메라를 방위각 90도로")
    assert t.kind == "done" and s.view.azimuth == 90
    assert session(tmp_path, "JSON 없음").turn("x").kind == "refused"
