"""서비스 층의 일: 팩 목록과 계산 호출. HTTP를 모르는 함수들이라 서버 없이도 시험한다."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Mapping

import yaml

from cont import packs

_ENGINES = Path(__file__).resolve().parents[3] / "config" / "physics" / "engines.yaml"


class NotFound(KeyError):
    pass


def list_packs() -> list[dict[str, Any]]:
    """쓸 수 있는 물리 팩과 그 한계. 한계는 숨기지 않는다."""
    info = {e["key"]: e for e in yaml.safe_load(_ENGINES.read_text(encoding="utf-8"))["engines"]}
    return [{"key": n, "name": info.get(n, {}).get("name", n), "summary": info.get(n, {}).get("summary", ""),
             "limits": info.get(n, {}).get("limits", "")} for n in packs.names()]


def new_run_id() -> str:
    return "run-" + uuid.uuid4().hex[:12]


def solve(name: str, inputs: Mapping[str, Any], question: str = "", action: str = "solve") -> dict[str, Any]:
    """팩을 불러 답변 묶음을 받는다. 실행 ID와 출처를 붙이며 값은 바꾸지 않는다. action은 팩이 내놓은 다른 동작 (기본 solve)."""
    if name not in packs.names():
        raise NotFound(name)
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs는 항목 이름과 값을 가진 객체여야 합니다")
    pack = packs.get(name)
    if action == "solve":
        fn = pack.solve
    else:
        fn = getattr(pack, "actions", {}).get(action)
        if fn is None:
            raise NotFound(f"{name}/{action}")
    answer = fn(inputs, question).stamped(f"pack:{name}" + ("" if action == "solve" else f":{action}"), run_id=new_run_id())
    body = {"run_id": answer.provenance.run_id, "revision_id": answer.revision_id(), "content_hash": answer.content_hash(),
            "answer": answer.to_dict(), "trust": answer.trust(), "truth_line": answer.truth_line()}
    return json.loads(json.dumps(body, ensure_ascii=False, default=str))     # 숫자 배열 등을 JSON으로 안전하게


def execute(name: str, inputs: Mapping[str, Any], question: str = "", action: str = "solve", *,
            project_id: str = "", asset_id: str = "", parent_run_id: str = "", lineage: Mapping[str, Any] | None = None,
            sources: list[str] | None = None) -> dict[str, Any]:
    """solve를 부르고 저장소가 켜져 있으면 실행 한 건으로 남긴다. 계산하지 못해도 실패 실행으로 남기고 오류는 그대로 올린다."""
    from cont.service import runs
    st = runs.store()
    base = {"created_at": runs.now(), "pack": name, "action": action, "question": question, "inputs": json.loads(json.dumps(inputs, default=str)),
            "model_version": runs.model_version(name), "project_id": project_id, "asset_id": asset_id, "parent_run_id": parent_run_id}
    if lineage is not None:                      # 학습한 모델이 낸 결과일 때만. 형식이 틀리거나 조각이 비면 계산 전에 거절한다
        from cont.learn.lineage import from_dict
        base["lineage"] = from_dict(lineage).to_dict()
    if sources:                                  # 근거로 쓴 자료: 장부에 있고 이 프로젝트의 것이어야 한다 (계산 전에 거절)
        from cont.service import ledger
        lg = ledger.configured()
        if lg is None:
            raise ValueError("근거 자료를 쓰려면 자료 장부가 켜져 있어야 합니다 (CONT_LEDGER_DIR)")
        if not project_id:
            raise ValueError("근거 자료를 쓰려면 project_id가 필요합니다")
        base["sources"] = [{"id": r["id"], "sha256": r["sha256"], "kind": r["kind"]} for r in lg.require_sources(list(sources), project_id)]
    try:
        body = solve(name, inputs, question, action)
    except NotFound:
        raise
    except Exception as exc:
        if st is not None:
            st.save({**base, "run_id": new_run_id(), "status": "failed", "error": str(exc), "response": None, "content_hash": "", "revision_id": ""})
        raise
    if st is not None:
        st.save({**base, "run_id": body["run_id"], "status": "complete", "error": "", "response": body,
                 "content_hash": body["content_hash"], "revision_id": body["revision_id"]})
    return {**body, "stored": st is not None}


def get_run(run_id: str) -> dict[str, Any]:
    from cont.service import runs
    st = runs.store()
    if st is None:
        raise NotFound("실행 저장소가 켜져 있지 않습니다 (CONT_RUN_DIR)")
    try:
        return st.get(run_id)
    except runs.RunNotFound:
        raise NotFound(run_id) from None


def list_runs(pack: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    from cont.service import runs
    st = runs.store()
    if st is None:
        raise NotFound("실행 저장소가 켜져 있지 않습니다 (CONT_RUN_DIR)")
    return st.list(pack, limit)


def recompute(run_id: str) -> dict[str, Any]:
    """같은 입력으로 새 실행을 만든다. 이전 실행은 그대로 남는다. 결과가 같은지와 모델 버전이 바뀌었는지를 알린다."""
    from cont.service import runs
    old = get_run(run_id)
    new = execute(old["pack"], old["inputs"], old.get("question", ""), old.get("action", "solve"),
                  project_id=old.get("project_id", ""), asset_id=old.get("asset_id", ""), parent_run_id=old["run_id"], lineage=old.get("lineage"),
                  sources=[x["id"] for x in old.get("sources", [])] or None)
    return {"run": new, "parent_run_id": old["run_id"],
            "same_content": bool(old.get("content_hash")) and old["content_hash"] == new["content_hash"],
            "model_version_changed": old.get("model_version") != runs.model_version(old["pack"])}
