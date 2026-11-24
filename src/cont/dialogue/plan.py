"""M01 계획 객체와 실행기(W3, A15·A16·A17 일부).

LLM의 출력은 이 모듈의 `Plan`으로만 받는다. 등록된 도구만 실행하고, 인자는 도구가 선언한 형식에 맞아야 한다.
의존한 단계가 실패하면 뒤 단계는 건너뛰고(skipped), 다시 실행할 때는 실패·건너뛴 단계만 돌린다. 임의의 코드나 쉘은 실행하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

MAX_STEPS = 32
STATES = ("pending", "running", "done", "failed", "skipped", "cancelled")


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    run: Callable[..., Mapping[str, Any]]
    args: Mapping[str, type]                       # 필수 인자 이름 → 형식
    optional: Mapping[str, type] = field(default_factory=dict)


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    args: Mapping[str, Any]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    steps: tuple[Step, ...]

    def request_id(self) -> str:
        body = [{"id": s.id, "tool": s.tool, "args": s.args, "depends_on": list(s.depends_on)} for s in self.steps]
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:16]


def parse(obj: Any) -> Plan:
    """LLM이 낸 JSON 모양(사전)을 계획으로 바꾼다. 모양이 맞지 않으면 PlanError."""
    if not isinstance(obj, Mapping) or not isinstance(obj.get("steps"), list):
        raise PlanError("계획은 {'steps': [...]} 모양이어야 합니다")
    steps = []
    for i, s in enumerate(obj["steps"]):
        if not isinstance(s, Mapping) or not isinstance(s.get("id"), str) or not isinstance(s.get("tool"), str):
            raise PlanError(f"{i + 1}번째 단계에 id와 tool(문자열)이 필요합니다")
        args, deps = s.get("args", {}), s.get("depends_on", [])
        if not isinstance(args, Mapping) or not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise PlanError(f"'{s['id']}' 단계의 args는 객체, depends_on은 문자열 목록이어야 합니다")
        steps.append(Step(s["id"], s["tool"], dict(args), tuple(deps)))
    return Plan(tuple(steps))


def validate(plan: Plan, tools: Mapping[str, Tool]) -> list[str]:
    """실행 순서(위상 정렬)를 돌려준다. 없는 도구, 중복·없는 의존, 순환, 인자 불일치는 PlanError."""
    if not plan.steps:
        raise PlanError("단계가 없습니다")
    if len(plan.steps) > MAX_STEPS:
        raise PlanError(f"단계가 너무 많습니다 ({len(plan.steps)} > {MAX_STEPS})")
    ids = [s.id for s in plan.steps]
    if len(set(ids)) != len(ids):
        raise PlanError("단계 id가 겹칩니다")
    for s in plan.steps:
        t = tools.get(s.tool)
        if t is None:
            raise PlanError(f"등록되지 않은 도구입니다: '{s.tool[:30]}'")
        missing = [k for k in t.args if k not in s.args]
        extra = [k for k in s.args if k not in t.args and k not in t.optional]
        if missing or extra:
            raise PlanError(f"'{s.id}' 단계 인자가 맞지 않습니다 (빠짐: {missing}, 모르는 인자: {extra})")
        for k, v in s.args.items():
            want = {**t.args, **t.optional}[k]
            if isinstance(v, bool) and want is not bool or not isinstance(v, want):
                raise PlanError(f"'{s.id}' 단계의 '{k}'는 {want.__name__} 형식이어야 합니다")
        for d in s.depends_on:
            if d not in ids:
                raise PlanError(f"'{s.id}' 단계가 없는 단계 '{d}'에 의존합니다")
            if d == s.id:
                raise PlanError(f"'{s.id}' 단계가 자기 자신에 의존합니다")
    order, left = [], {s.id: set(s.depends_on) for s in plan.steps}
    while left:
        ready = sorted(k for k, v in left.items() if not v)
        if not ready:
            raise PlanError("의존 관계에 순환이 있습니다")
        for k in ready:
            order.append(k); del left[k]
        for v in left.values():
            v.difference_update(ready)
    return order


@dataclass
class StepState:
    state: str = "pending"
    result: Mapping[str, Any] | None = None
    error: str = ""
    attempts: int = 0


@dataclass
class Run:
    plan: Plan
    states: dict[str, StepState]
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return all(s.state == "done" for s in self.states.values())


class Executor:
    def __init__(self, tools: Mapping[str, Tool]):
        self.tools = dict(tools)
        self._runs: dict[str, Run] = {}              # 같은 계획은 한 번만 실행한다 (요청 ID 기준)
        self.cancelled: set[str] = set()

    def cancel(self, request_id: str) -> None:
        self.cancelled.add(request_id)

    def execute(self, plan: Plan, deadline_s: float | None = None) -> Run:
        """처음이면 실행하고, 같은 계획이 이미 있으면 실패·건너뛴 단계만 다시 돌린다 (끝난 단계는 다시 실행하지 않는다)."""
        order = validate(plan, self.tools)
        rid = plan.request_id()
        run = self._runs.get(rid) or Run(plan, {s.id: StepState() for s in plan.steps})
        self._runs[rid] = run
        by_id = {s.id: s for s in plan.steps}
        t_end = None if deadline_s is None else time.monotonic() + deadline_s
        for sid in order:
            st, step = run.states[sid], by_id[sid]
            if st.state == "done":
                continue
            if rid in self.cancelled or (t_end is not None and time.monotonic() > t_end):
                st.state = "cancelled"; self._event(run, sid, "cancelled"); continue
            if any(run.states[d].state != "done" for d in step.depends_on):
                st.state, st.error = "skipped", "앞 단계가 끝나지 않아 건너뜀"; self._event(run, sid, "skipped"); continue
            st.state, st.error = "running", ""; st.attempts += 1; self._event(run, sid, "running")
            try:
                out = self.tools[step.tool].run(**step.args)
                if not isinstance(out, Mapping) or not out:
                    raise RuntimeError("도구가 빈 결과를 돌려주었습니다 (산출물이 없으면 끝난 것으로 보지 않습니다)")
                st.result, st.state = dict(out), "done"
            except Exception as exc:                  # 도구 오류는 그 단계의 실패로 남기고 뒤 단계를 막는다
                st.state, st.error, st.result = "failed", f"{type(exc).__name__}: {str(exc)[:200]}", None
            self._event(run, sid, st.state)
        return run

    @staticmethod
    def _event(run: Run, sid: str, state: str) -> None:
        run.events.append({"step": sid, "state": state, "n": len(run.events)})


def default_tools() -> dict[str, Tool]:
    """실제로 있는 도구만 등록한다. 설명·이미지·그래프 같은 도구는 구현되면 여기에 더한다 (가짜로 채우지 않는다)."""
    from cont.service import api

    def solve_physics(pack: str, inputs: dict, question: str = "") -> Mapping[str, Any]:
        return api.execute(pack, inputs, question)

    return {"solve_physics": Tool("solve_physics", solve_physics, {"pack": str, "inputs": dict}, {"question": str})}
