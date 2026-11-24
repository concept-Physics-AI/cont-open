"""체결 대화 세션 + 계획 실행기."""
from cont.dialogue.fastening_chat import Session
from cont.dialogue.plan import Executor, Step, Plan, parse
from cont.dialogue.plan_tools import fastening_tools
from cont.dialogue.serve_fastening import example


def new():
    j, l = example()
    s = Session(j, l)
    return s, Executor(fastening_tools(s))


def test_plan_applies_changes_in_order_through_the_same_checks():
    s, ex = new()
    plan = parse({"steps": [{"id": "a", "tool": "fastening_change", "args": {"changes": {"tightening_torque": 70}}},
                            {"id": "b", "tool": "fastening_change", "args": {"changes": {"property_class": "8.8"}}, "depends_on": ["a"]}]})
    run = ex.execute(plan)
    assert run.done and s.load.tightening_torque == 70.0 and s.joint.property_class == "8.8"
    assert run.states["b"].result["applied_changes"] == {"property_class": "8.8"}


def test_bad_change_fails_the_step_and_skips_followers_without_changing_the_joint():
    s, ex = new(); before = (s.joint, s.load)
    plan = parse({"steps": [{"id": "a", "tool": "fastening_change", "args": {"changes": {"size": "M99"}}},
                            {"id": "b", "tool": "fastening_change", "args": {"changes": {"tightening_torque": 70}}, "depends_on": ["a"]}]})
    run = ex.execute(plan)
    assert [run.states[k].state for k in "ab"] == ["failed", "skipped"] and (s.joint, s.load) == before


def test_unknown_key_and_wrong_tool_use_are_refused():
    s, ex = new()
    run = ex.execute(parse({"steps": [{"id": "a", "tool": "fastening_change", "args": {"changes": {"__import__": 1}}}]}))
    assert run.states["a"].state == "failed"
    run = ex.execute(parse({"steps": [{"id": "x", "tool": "fastening_change", "args": {"changes": {"targets": {"safety_yield": 1.5}}}}]}))
    assert run.states["x"].state == "failed"


def test_recommend_then_choose_applies_an_offer():
    s, ex = new()
    plan = parse({"steps": [{"id": "r", "tool": "fastening_recommend", "args": {"targets": {"safety_yield": 1.2}}},
                            {"id": "c", "tool": "fastening_choose", "args": {"n": 2}, "depends_on": ["r"]}]})
    run = ex.execute(plan)
    assert run.states["r"].state == "done" and run.states["r"].result["outcome"] == "offer"
    assert run.states["c"].state == "done" and run.states["c"].result["applied_changes"]     # 2번은 실제로 바꾸는 추천


def test_choosing_the_unchanged_offer_is_a_failed_step():
    s, ex = new()
    run = ex.execute(parse({"steps": [{"id": "r", "tool": "fastening_recommend", "args": {"targets": {"safety_yield": 1.2}}},
                                      {"id": "c", "tool": "fastening_choose", "args": {"n": 1}, "depends_on": ["r"]}]}))
    assert run.states["c"].state == "failed"                  # 1번은 지금 그대로라 바꾼 것이 없다
