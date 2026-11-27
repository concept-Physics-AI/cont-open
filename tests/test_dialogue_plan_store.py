"""A15: 계획 체크포인트와 재개."""
import json

import pytest

from cont.dialogue.plan import Executor, Plan, Step, Tool
from cont.dialogue.plan_store import StaleCheckpoint, load, resume, save

CTX = {"code_sha": "abc1234", "target_revision": "r1"}


def build(log, fail):
    def ok(x: int):
        log.append(x)
        if fail["on"] and x == 2:
            raise RuntimeError("공급자 오류")
        return {"v": x}
    return Executor({"ok": Tool("ok", ok, {"x": int})})


def plan():
    return Plan((Step("a", "ok", {"x": 1}), Step("b", "ok", {"x": 2}, ("a",)), Step("c", "ok", {"x": 3}, ("b",))))


def test_resume_runs_only_unfinished_steps(tmp_path):
    log = []; fail = {"on": True}; p = plan()
    ex = build(log, fail); run = ex.execute(p); save(tmp_path, p, run, CTX)
    assert [run.states[k].state for k in "abc"] == ["done", "failed", "skipped"]
    fail["on"] = False; log.clear()
    ex2 = build(log, fail)                                             # 새 프로세스를 흉내: 실행기도 새것
    out = resume(ex2, tmp_path, p, CTX)
    assert out.done and log == [2, 3]                                  # a는 다시 실행하지 않았다


def test_stale_context_plan_or_tamper_is_refused(tmp_path):
    log = []; p = plan(); run = build(log, {"on": False}).execute(p); path = save(tmp_path, p, run, CTX)
    with pytest.raises(StaleCheckpoint, match="맥락"):
        load(tmp_path, p, {**CTX, "target_revision": "r2"})            # 대상이 바뀌었다
    with pytest.raises(StaleCheckpoint, match="맥락.*code_sha"):
        load(tmp_path, p, {**CTX, "code_sha": "zzz"})                  # 코드가 바뀌었다
    other = Plan((Step("a", "ok", {"x": 9}),))
    with pytest.raises(StaleCheckpoint, match="없습니다"):
        load(tmp_path, other, CTX)
    rec = json.loads(path.read_text(encoding="utf-8")); rec["steps"]["a"]["result"] = {"v": 99}
    path.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(StaleCheckpoint, match="해시"):
        load(tmp_path, p, CTX)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StaleCheckpoint, match="깨졌"):
        load(tmp_path, p, CTX)


def test_step_that_was_running_at_save_time_is_not_treated_as_done(tmp_path):
    log = []; p = plan(); ex = build(log, {"on": False}); run = ex.execute(p)
    run.states["b"].state, run.states["b"].result = "running", None    # 저장 직후 죽은 상황을 만든다
    run.states["c"].state, run.states["c"].result = "pending", None
    save(tmp_path, p, run, CTX)
    restored = load(tmp_path, p, CTX)
    assert restored.states["b"].state == "failed" and "결과를 알 수 없음" in restored.states["b"].error
    assert restored.states["a"].state == "done"


# ---- 실행 전 요청 기록 ---------------------------------------------------------------------------------------------
def test_request_record_round_trips_and_is_cleared(tmp_path):
    from cont.dialogue.plan_store import clear_request, has_request, load_request, save_request
    p = plan()
    assert not has_request(tmp_path)
    save_request(tmp_path, "일을 해줘", p, {"rev": 1})
    assert has_request(tmp_path)
    text, got, ctx = load_request(tmp_path)
    assert text == "일을 해줘" and got == p and got.request_id() == p.request_id() and ctx == {"rev": 1}
    assert clear_request(tmp_path) is True and clear_request(tmp_path) is False and not has_request(tmp_path)


def test_request_record_refuses_missing_corrupt_and_tampered(tmp_path):
    from cont.dialogue.plan_store import load_request, save_request
    with pytest.raises(StaleCheckpoint, match="없습니다"):
        load_request(tmp_path)
    path = save_request(tmp_path, "x", plan(), {})
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["plan"]["steps"][0]["args"]["x"] = 99                       # 손으로 고침
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(StaleCheckpoint, match="해시"):
        load_request(tmp_path)
    path.write_text("{깨짐", encoding="utf-8")
    with pytest.raises(StaleCheckpoint, match="깨졌"):
        load_request(tmp_path)
