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


def solve(name: str, inputs: Mapping[str, Any], question: str = "") -> dict[str, Any]:
    """팩을 불러 답변 묶음을 받는다. 실행 ID와 출처를 붙이며 값은 바꾸지 않는다."""
    if name not in packs.names():
        raise NotFound(name)
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs는 항목 이름과 값을 가진 객체여야 합니다")
    answer = packs.get(name).solve(inputs, question).stamped(f"pack:{name}", run_id=new_run_id())
    body = {"run_id": answer.provenance.run_id, "revision_id": answer.revision_id(), "content_hash": answer.content_hash(),
            "answer": answer.to_dict(), "trust": answer.trust()}
    return json.loads(json.dumps(body, ensure_ascii=False, default=str))     # 숫자 배열 등을 JSON으로 안전하게
