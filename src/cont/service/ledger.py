"""원본과 파생물의 지문·부모 관계(A26). 근거로 쓴 자료가 바뀌었거나 다른 프로젝트의 것이면 근거로 남지 않게 한다.

항목은 쓰고 나면 고치지 않는다. ID는 (종류, 내용 SHA-256, 부모 ID들, 프로젝트)의 해시라서 같은 내용도 부모나 프로젝트가 다르면 다른 항목이다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_CFG = Path(__file__).resolve().parents[3] / "config" / "service.yaml"
_ID = re.compile(r"^art-[0-9a-f]{16}$")
KINDS = ("source", "page", "frame", "derived")


class LedgerError(ValueError):
    pass


def configured() -> "Ledger | None":
    import yaml
    d = os.environ.get("CONT_LEDGER_DIR") or (yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}).get("ledger_dir") or ""
    return Ledger(d) if d else None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Ledger:
    def __init__(self, root: str | Path):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, art_id: str) -> Path:
        if not isinstance(art_id, str) or not _ID.fullmatch(art_id):
            raise LedgerError(f"올바르지 않은 항목 ID: {str(art_id)[:30]!r}")
        return self.root / f"{art_id}.json"

    def get(self, art_id: str) -> dict[str, Any]:
        p = self._path(art_id)
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise LedgerError(f"없는 항목입니다: {art_id}") from None
        except (ValueError, UnicodeError):
            raise LedgerError(f"{art_id}: 기록이 깨졌습니다") from None
        if not isinstance(rec, dict) or rec.get("id") != art_id or rec.get("id") != self._make_id(rec["kind"], rec["sha256"], rec["parents"], rec["project_id"]):
            raise LedgerError(f"{art_id}: 기록의 ID가 내용과 맞지 않습니다")
        return rec

    @staticmethod
    def _make_id(kind: str, sha: str, parents: list[str], project_id: str) -> str:
        body = json.dumps({"kind": kind, "sha256": sha, "parents": sorted(parents), "project_id": project_id}, sort_keys=True)
        return "art-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    def register(self, kind: str, data: bytes, project_id: str, parents: tuple[str, ...] = (), label: str = "") -> dict[str, Any]:
        if kind not in KINDS:
            raise LedgerError(f"종류는 {', '.join(KINDS)} 중 하나여야 합니다")
        if not project_id:
            raise LedgerError("프로젝트 ID가 필요합니다")
        if kind == "source" and parents:
            raise LedgerError("원본(source)에는 부모가 없습니다")
        if kind != "source" and not parents:
            raise LedgerError("파생 항목에는 부모가 하나 이상 필요합니다 (원본을 먼저 등록하세요)")
        for pid in parents:
            par = self.get(pid)                                   # 없거나 깨진 부모는 거절
            if par["project_id"] != project_id:
                raise LedgerError(f"다른 프로젝트의 자료는 부모가 될 수 없습니다: {pid}")
        sha = sha256_bytes(data)
        art_id = self._make_id(kind, sha, list(parents), project_id)
        rec = {"id": art_id, "kind": kind, "sha256": sha, "parents": sorted(parents), "project_id": project_id, "label": label[:80], "size": len(data)}
        path = self._path(art_id)
        if path.exists():
            return self.get(art_id)                               # 같은 항목은 한 번만 쓴다
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, sort_keys=True); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return rec

    def ancestors(self, art_id: str) -> list[str]:
        seen: list[str] = []
        stack = [art_id]
        while stack:
            cur = stack.pop()
            for p in self.get(cur)["parents"]:
                if p not in seen:
                    seen.append(p); stack.append(p)
        return seen

    def check_content(self, art_id: str, data: bytes) -> None:
        """지금 가진 파일이 등록된 지문과 같은지 확인한다. 다르면 근거로 쓸 수 없다."""
        rec = self.get(art_id)
        if sha256_bytes(data) != rec["sha256"]:
            raise LedgerError(f"{art_id}: 파일이 등록 때와 다릅니다 (바뀌었거나 다른 파일로 대체됨). 근거로 쓰지 않습니다")

    def require_sources(self, ids: list[str], project_id: str) -> list[dict[str, Any]]:
        """실행에 근거로 쓸 항목들이 모두 있고 이 프로젝트의 것인지 확인한다."""
        out = []
        for i in ids:
            rec = self.get(i)
            if rec["project_id"] != project_id:
                raise LedgerError(f"다른 프로젝트의 자료는 근거로 쓸 수 없습니다: {i}")
            out.append(rec)
        return out
