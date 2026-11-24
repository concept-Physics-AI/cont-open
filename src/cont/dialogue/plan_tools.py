"""체결 대화 세션을 계획 실행기의 도구로 내놓는다. 도구는 세션의 같은 검사(허용 항목·형식, 체결 팩 재계산)를 거친다.

바꾸지 못했거나 바꿀 것이 없으면 그 단계는 실패다(실패한 것을 끝난 것으로 보고하지 않는다).
"""
from __future__ import annotations

from typing import Any, Mapping

from cont.dialogue.fastening_chat import Session, Turn, brief
from cont.dialogue.plan import Tool


def _done(turn: Turn) -> Mapping[str, Any]:
    if turn.kind in ("failed", "none"):
        raise RuntimeError(turn.reply.splitlines()[0] if turn.reply else "처리하지 못했습니다")
    return {"outcome": turn.kind, "applied_changes": dict(turn.changes), "reply": turn.reply}


def fastening_tools(session: Session) -> dict[str, Tool]:
    def change(changes: dict) -> Mapping[str, Any]:
        if "targets" in changes or "choose" in changes:
            raise ValueError("목표와 선택은 recommend, choose 도구로 하세요")
        return _done(session.apply_changes(changes))

    def recommend(targets: dict) -> Mapping[str, Any]:
        return _done(session.apply_changes({"targets": targets}))

    def choose(n: int) -> Mapping[str, Any]:
        return _done(session.apply_changes({"choose": n}))

    return {"fastening_change": Tool("fastening_change", change, {"changes": dict}),
            "fastening_recommend": Tool("fastening_recommend", recommend, {"targets": dict}),
            "fastening_choose": Tool("fastening_choose", choose, {"n": int})}
