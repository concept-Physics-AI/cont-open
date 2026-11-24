"""모델 계보(A05): 데이터 지문 → 분할 지문 → 학습 기록 → 모델 파일 해시 → 평가 버전을 하나로 묶어 실행 결과에 붙인다.

같은 코드라도 데이터나 가중치 개정이 바뀌면 계보 ID가 달라지고, 계보에 적힌 모델 파일이 지금 파일과 다르면 거절한다.
조각이 하나라도 비어 있으면 계보를 만들지 않는다 (빈 값으로 채우지 않는다).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

PARTS = ("dataset_sha256", "split_fingerprint", "training_fingerprint", "model_sha256", "evaluation_version", "code_sha")


class LineageError(ValueError):
    pass


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_sha256(rows: Any) -> str:
    """행 목록(JSON으로 쓸 수 있는 값)의 지문. 순서까지 포함한다."""
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Lineage:
    dataset_sha256: str
    split_fingerprint: str
    training_fingerprint: str
    model_sha256: str
    evaluation_version: str
    code_sha: str

    def __post_init__(self):
        for k in PARTS:
            v = getattr(self, k)
            if not isinstance(v, str) or not v.strip():
                raise LineageError(f"계보의 '{k}'가 비어 있습니다. 비워 둔 채 계보를 만들지 않습니다")

    def to_dict(self) -> dict[str, str]:
        d = {k: getattr(self, k) for k in PARTS}
        d["lineage_id"] = hashlib.sha256(json.dumps(d, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return d


def from_dict(d: Mapping[str, Any]) -> Lineage:
    if not isinstance(d, Mapping):
        raise LineageError("계보가 객체가 아닙니다")
    missing = [k for k in PARTS if k not in d]
    if missing:
        raise LineageError(f"계보에 빠진 항목: {', '.join(missing)}")
    lin = Lineage(**{k: d[k] for k in PARTS})
    if "lineage_id" in d and d["lineage_id"] != lin.to_dict()["lineage_id"]:
        raise LineageError("계보 ID가 내용과 맞지 않습니다 (고쳐진 기록일 수 있습니다)")
    return lin


def attach(record: Mapping[str, Any], lineage: Lineage) -> dict[str, Any]:
    """실행 기록 복사본에 계보를 붙인다. 이미 다른 계보가 있으면 덮어쓰지 않고 거절한다."""
    out = dict(record)
    new = lineage.to_dict()
    if "lineage" in out and out["lineage"] != new:
        raise LineageError("이 기록에는 이미 다른 계보가 붙어 있습니다")
    out["lineage"] = new
    return out


def verify(d: Mapping[str, Any], model_path: str | Path, dataset_sha: str | None = None, evaluation_version: str | None = None) -> Lineage:
    """기록의 계보가 지금의 모델 파일(·데이터·평가 버전)과 같은지 확인한다. 다르면 무엇이 다른지 적어 거절한다."""
    lin = from_dict(d)
    bad = []
    try:
        now = file_sha256(model_path)
    except OSError:
        raise LineageError("계보에 적힌 모델 파일을 읽을 수 없습니다 (없어졌거나 위치가 바뀜)") from None
    if now != lin.model_sha256:
        bad.append("모델 파일(가중치 개정이 다름)")
    if dataset_sha is not None and dataset_sha != lin.dataset_sha256:
        bad.append("데이터 개정")
    if evaluation_version is not None and evaluation_version != lin.evaluation_version:
        bad.append("평가 버전")
    if bad:
        raise LineageError("계보와 현재 자원이 다릅니다: " + ", ".join(bad))
    return lin
