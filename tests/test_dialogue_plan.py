"""M01 계획 객체·실행기 (A15·A16·A17 일부)."""
import pytest

from cont.dialogue.plan import Executor, Plan, PlanError, Step, Tool, default_tools, parse, validate


def tools(log, fail=None):
    def ok(x: int):
        log.append(("ok", x)); return {"value": x}
    def flaky(x: int):
        log.append(("flaky", x))
        if fail and fail["on"]:
            raise RuntimeError("공급자 오류")
        return {"value": x}
    def empty(x: int):
        return {}
    return {"ok": Tool("ok", ok, {"x": int}), "flaky": Tool("flaky", flaky, {"x": int}), "empty": Tool("empty", empty, {"x": int})}


def plan(*steps):
    return Plan(tuple(steps))


def test_parse_and_validate_reject_bad_plans():
    t = tools([])
    with pytest.raises(PlanError):
        parse({"steps": "no"})
    with pytest.raises(PlanError, match="등록되지"):
        validate(plan(Step("a", "rm_rf", {})), t)
    with pytest.raises(PlanError, match="인자"):
        validate(plan(Step("a", "ok", {"x": 1, "y": 2})), t)
    with pytest.raises(PlanError, match="형식"):
        validate(plan(Step("a", "ok", {"x": "1"})), t)
    with pytest.raises(PlanError, match="형식"):
        validate(plan(Step("a", "ok", {"x": True})), t)
    with pytest.raises(PlanError, match="없는 단계"):
        validate(plan(Step("a", "ok", {"x": 1}, ("zz",))), t)
    with pytest.raises(PlanError, match="순환"):
        validate(plan(Step("a", "ok", {"x": 1}, ("b",)), Step("b", "ok", {"x": 1}, ("a",))), t)
    with pytest.raises(PlanError, match="겹칩"):
        validate(plan(Step("a", "ok", {"x": 1}), Step("a", "ok", {"x": 2})), t)
    with pytest.raises(PlanError, match="단계가 없"):
        validate(plan(), t)


def test_executes_in_dependency_order():
    log = []; ex = Executor(tools(log))
    run = ex.execute(plan(Step("b", "ok", {"x": 2}, ("a",)), Step("a", "ok", {"x": 1})))
    assert run.done and [x for _, x in log] == [1, 2]


def test_failed_dependency_skips_followers_and_retry_runs_only_those():
    log = []; fail = {"on": True}; ex = Executor(tools(log, fail))
    p = plan(Step("a", "ok", {"x": 1}), Step("b", "flaky", {"x": 2}, ("a",)), Step("c", "ok", {"x": 3}, ("b",)))
    run = ex.execute(p)
    assert [run.states[k].state for k in "abc"] == ["done", "failed", "skipped"]
    fail["on"] = False
    run2 = ex.execute(p)                                              # 같은 계획을 다시: a는 다시 실행하지 않는다
    assert run2 is run and run2.done and log.count(("ok", 1)) == 1 and run2.states["b"].attempts == 2


def test_duplicate_request_runs_once_and_empty_result_is_not_done():
    log = []; ex = Executor(tools(log)); p = plan(Step("a", "ok", {"x": 1}))
    ex.execute(p); ex.execute(p)
    assert log == [("ok", 1)]
    r = ex.execute(plan(Step("e", "empty", {"x": 1})))
    assert r.states["e"].state == "failed" and "빈 결과" in r.states["e"].error


def test_cancel_discards_remaining_steps():
    log = []; ex = Executor(tools(log)); p = plan(Step("a", "ok", {"x": 1}))
    ex.cancel(p.request_id())
    run = ex.execute(p)
    assert run.states["a"].state == "cancelled" and log == []


def test_default_tools_only_register_real_tools_and_run_a_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("CONT_RUN_DIR", str(tmp_path / "runs"))
    t = default_tools()
    assert set(t) == {"solve_physics"}
    run = Executor(t).execute(plan(Step("s", "solve_physics", {"pack": "heat", "inputs": {"case": "sine_1d"}})))
    assert run.done and run.states["s"].result["run_id"].startswith("run-")


def test_cancel_during_a_step_discards_its_late_result_and_stops_followers():
    import threading
    started, release = threading.Event(), threading.Event()
    log = []

    def slow(x: int):
        started.set(); release.wait(5); log.append(x); return {"value": x}

    ex = Executor({"slow": Tool("slow", slow, {"x": int}), **tools(log)})
    p = plan(Step("a", "slow", {"x": 1}), Step("b", "ok", {"x": 2}, ("a",)))
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("run", ex.execute(p))); th.start()
    assert started.wait(5)
    ex.cancel(p.request_id()); release.set(); th.join(5)
    run = out["run"]
    assert run.states["a"].state == "cancelled" and run.states["a"].result is None
    assert run.states["b"].state in ("skipped", "cancelled") and ("ok", 2) not in log


def test_two_simultaneous_identical_requests_run_each_step_once():
    import threading
    log = []; gate = threading.Event()

    def slow(x: int):
        gate.wait(5); log.append(x); return {"value": x}

    ex = Executor({"slow": Tool("slow", slow, {"x": int})}); p = plan(Step("a", "slow", {"x": 1}))
    results = []
    ts = [threading.Thread(target=lambda: results.append(ex.execute(p))) for _ in range(2)]
    [t.start() for t in ts]; gate.set(); [t.join(5) for t in ts]
    assert log == [1] and len(results) == 2 and all(r.done for r in results)
