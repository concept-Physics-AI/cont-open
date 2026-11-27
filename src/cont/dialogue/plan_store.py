"""계획 실행의 체크포인트(A15): 중단된 실행을 다시 이어 가되, 오래된 상태를 조용히 되살리지 않는다.

기록에는 계획 요청 ID, 단계별 상태·결과, 그리고 호출한 쪽이 정한 맥락(코드 SHA, 대상 개정 등)이 들어간다.
다시 불러올 때 계획이나 맥락이 다르면 StaleCheckpoint로 거절한다. 저장 시점에 실행 중이던 단계는 결과를 알 수 없으므로
끝난 것으로 보지 않고 실패로 돌려, 다시 실행할지는 실행기가 정하게 한다(조용히 건너뛰지도, 몰래 다시 하지도 않는다).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cont.dialogue.plan import Executor, Plan, Run, StepState, parse


class StaleCheckpoint(ValueError):
    pass


def _digest(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def save(root: str | Path, plan: Plan, run: Run, context: Mapping[str, Any]) -> Path:
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    body = {"request_id": plan.request_id(), "context": json.loads(json.dumps(context, sort_keys=True, default=str)),
            "steps": {k: {"state": v.state, "result": v.result, "error": v.error, "attempts": v.attempts} for k, v in run.states.items()},
            "events": run.events}
    rec = {**body, "sha256": _digest(body)}
    path = root / f"plan-{plan.request_id()}.json"
    fd, tmp = tempfile.mkstemp(dir=root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, sort_keys=True, default=str); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def load(root: str | Path, plan: Plan, context: Mapping[str, Any]) -> Run:
    path = Path(root) / f"plan-{plan.request_id()}.json"
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StaleCheckpoint("이 계획의 체크포인트가 없습니다") from None
    except (ValueError, UnicodeError):
        raise StaleCheckpoint("체크포인트를 읽을 수 없습니다 (깨졌습니다)") from None
    if not isinstance(rec, dict) or "sha256" not in rec:
        raise StaleCheckpoint("체크포인트 모양이 맞지 않습니다")
    body = {k: v for k, v in rec.items() if k != "sha256"}
    if rec["sha256"] != _digest(body):
        raise StaleCheckpoint("체크포인트의 해시가 맞지 않습니다 (고쳐졌거나 깨졌습니다)")
    if rec.get("request_id") != plan.request_id():
        raise StaleCheckpoint("체크포인트가 다른 계획의 것입니다")
    want = json.loads(json.dumps(context, sort_keys=True, default=str))
    if rec.get("context") != want:
        diff = sorted(k for k in set(want) | set(rec.get("context") or {}) if want.get(k) != (rec.get("context") or {}).get(k))
        raise StaleCheckpoint(f"맥락이 달라져 이어 가지 않습니다: {', '.join(diff)}")
    states = {}
    for s in plan.steps:
        raw = rec["steps"].get(s.id)
        if raw is None:
            raise StaleCheckpoint(f"체크포인트에 '{s.id}' 단계가 없습니다")
        st = StepState(raw["state"], raw["result"], raw["error"], raw["attempts"])
        if st.state == "running":                     # 저장 시점에 돌고 있던 단계: 결과를 모른다
            st.state, st.result, st.error = "failed", None, "중단되어 결과를 알 수 없음 (다시 실행하면 부작용이 겹칠 수 있음)"
        states[s.id] = st
    return Run(plan, states, list(rec.get("events", [])))


def resume(ex: Executor, root: str | Path, plan: Plan, context: Mapping[str, Any]) -> Run:
    """체크포인트를 불러와 실행기에 올리고 남은 단계만 실행한다. 끝난 단계는 다시 실행하지 않는다."""
    run = load(root, plan, context)
    ex._runs[plan.request_id()] = run                 # 같은 요청 ID로 이어서 실행
    out = ex.execute(plan)
    save(root, plan, out, context)
    return out


# ---- 실행 전 요청 기록(write-ahead) ---------------------------------------------------------------------------
# 단계 상태가 아니라 '무엇을 하려던 요청인가'를 실행 전에 남긴다. 실행 중 프로세스가 죽으면 이 기록만 남아, 다시 열었을 때
# 사용자에게 알리고(조용히 이어 가지 않는다) 같은 계획을 다시 실행할지 버릴지 사용자가 정하게 한다.
REQUEST_FILE = "request.json"


def save_request(root: str | Path, text: str, plan: Plan, context: Mapping[str, Any]) -> Path:
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    body = {"text": text, "request_id": plan.request_id(),
            "plan": {"steps": [{"id": s.id, "tool": s.tool, "args": dict(s.args), "depends_on": list(s.depends_on)} for s in plan.steps]},
            "context": json.loads(json.dumps(context, sort_keys=True, default=str))}
    rec = {**body, "sha256": _digest(body)}
    path = root / REQUEST_FILE
    fd, tmp = tempfile.mkstemp(dir=root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, sort_keys=True, default=str); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def has_request(root: str | Path) -> bool:
    return (Path(root) / REQUEST_FILE).exists()


def load_request(root: str | Path) -> tuple[str, Plan, dict[str, Any]]:
    """남아 있는 요청 기록을 읽는다. 없거나 깨졌거나 해시가 맞지 않으면 StaleCheckpoint."""
    path = Path(root) / REQUEST_FILE
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StaleCheckpoint("중단된 요청 기록이 없습니다") from None
    except (ValueError, UnicodeError):
        raise StaleCheckpoint("중단된 요청 기록을 읽을 수 없습니다 (깨졌습니다)") from None
    if not isinstance(rec, dict) or "sha256" not in rec or not isinstance(rec.get("text"), str):
        raise StaleCheckpoint("중단된 요청 기록의 모양이 맞지 않습니다")
    body = {k: v for k, v in rec.items() if k != "sha256"}
    if rec["sha256"] != _digest(body):
        raise StaleCheckpoint("중단된 요청 기록의 해시가 맞지 않습니다 (고쳐졌거나 깨졌습니다)")
    try:
        plan = parse(rec["plan"])
    except ValueError as e:
        raise StaleCheckpoint(f"중단된 요청의 계획을 읽을 수 없습니다: {e}") from None
    if plan.request_id() != rec.get("request_id"):
        raise StaleCheckpoint("중단된 요청의 계획이 기록과 다릅니다")
    return rec["text"], plan, dict(rec.get("context") or {})


def clear_request(root: str | Path) -> bool:
    try:
        (Path(root) / REQUEST_FILE).unlink()
        return True
    except FileNotFoundError:
        return False
