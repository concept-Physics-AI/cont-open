"""체결 팩 표준 데이터 읽기. 숫자는 tables/iso_metric.yaml에만 있다."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DATA_FILE = Path(__file__).parent / "tables" / "iso_metric.yaml"


@dataclass(frozen=True)
class ThreadSize:
    designation: str
    d: float
    pitch_coarse: float
    hole_medium: float
    head_bearing_dw: float
    across_flats: float
    head_height: float
    nut_height: float


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def thread_size(designation: str) -> ThreadSize:
    key = designation.strip().upper()
    try:
        row = _data()["threads"][key]
    except KeyError:
        raise ValueError(f"thread '{designation}' is not in {DATA_FILE.name} (available: {thread_sizes()})") from None
    return ThreadSize(key, **{k: float(v) for k, v in row.items()})


def thread_sizes() -> list[str]:
    return list(_data()["threads"])


def yield_strength(property_class: str, d: float) -> float:
    try:
        rows = _data()["property_classes"][str(property_class)]["rp02"]
    except KeyError:
        raise ValueError(
            f"property class '{property_class}' is not in {DATA_FILE.name} (available: {property_classes()})"
        ) from None
    for d_max, rp in rows:
        if d <= float(d_max):
            return float(rp)
    raise ValueError(f"no Rp0.2 entry for class {property_class} at d={d}")


def property_classes() -> list[str]:
    return list(_data()["property_classes"])


def vdi_constant(name: str) -> float:
    return float(_data()["vdi2230"][name])


def shape_constant(name: str) -> float:
    return float(_data()["shape"][name])
