"""실행 저장: 계산 한 번을 파일 한 건으로 남기고 다시 읽는다 (ARCHITECTURE.md "실행 저장").

한 번 쓴 기록은 고치지 않는다. 읽을 때 기록 전체의 해시를 확인한다. 저장 위치는 설정에서만 받는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

import cont

_CFG = Path(__file__).resolve().parents[3] / "config" / "service.yaml"
_ID = re.compile(r"^run-[0-9a-f]{12}$")


class RunNotFound(KeyError):
    pass


class RunCorrupt(ValueError):
    pass


def configured_dir() -> Path | None:
    d = os.environ.get("CONT_RUN_DIR") or (yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}).get("run_dir") or ""
    return Path(d) if d else None


def model_version(pack: str) -> dict[str, str]:
    return {"code": cont.__version__, "pack": pack}


def _digest(rec: Mapping[str, Any]) -> str:
    body = {k: v for k, v in rec.items() if k != "record_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class RunStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not _ID.match(run_id):
            raise RunNotFound(run_id)
        return self.root / f"{run_id}.json"

    def save(self, rec: Mapping[str, Any]) -> dict[str, Any]:
        rec = dict(rec)
        rec["record_sha256"] = _digest(rec)
        path = self._path(rec["run_id"])
        if path.exists():
            raise FileExistsError(f"{rec['run_id']}는 이미 있습니다 (기록은 고치지 않습니다)")
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)
        return rec

    def get(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            raise RunNotFound(run_id)
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("record_sha256") != _digest(rec):
            raise RunCorrupt(f"{run_id}: 기록의 해시가 맞지 않습니다. 읽지 않습니다")
        return rec

    def list(self, pack: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        out = []
        for p in self.root.glob("run-*.json"):
            try:
                r = self.get(p.stem)
            except (RunCorrupt, ValueError):
                out.append({"run_id": p.stem, "status": "corrupt"})
                continue
            if pack is None or r.get("pack") == pack:
                out.append({k: r.get(k) for k in ("run_id", "created_at", "pack", "action", "status", "project_id", "asset_id", "parent_run_id", "content_hash", "revision_id", "model_version")})
        out.sort(key=lambda r: (r.get("created_at") or "", r["run_id"]), reverse=True)
        return out[: max(1, int(limit))]


def store() -> RunStore | None:
    d = configured_dir()
    return RunStore(d) if d else None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
