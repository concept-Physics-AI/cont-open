"""단위 정규화(R07). 표는 config/units.yaml. 모르는 단위나 차원이 다른 변환은 값을 만들지 않고 거절한다."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

CONFIG = Path(__file__).resolve().parents[3] / "config" / "units.yaml"


class UnitError(ValueError):
    pass


@lru_cache(maxsize=1)
def _table() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def canonical(unit: str) -> str:
    u = unit.strip()
    u = _table().get("aliases", {}).get(u, u)
    if u not in _table()["units"]:
        raise UnitError(f"모르는 단위입니다: '{unit.strip()[:20]}'. 지원 단위는 config/units.yaml에 있습니다")
    return u


def dimension(unit: str) -> str:
    return _table()["units"][canonical(unit)]["dim"]


def convert(value, src: str, dst: str):
    """value를 src 단위에서 dst 단위로 바꾼다. 스칼라와 배열 모두 가능하다. 차원이 다르면 UnitError."""
    a, b = canonical(src), canonical(dst)
    ua, ub = _table()["units"][a], _table()["units"][b]
    if ua["dim"] != ub["dim"]:
        hint = " (절대 온도와 온도 차는 다른 양입니다. 차이는 ddegC처럼 적어 주세요)" if {ua["dim"], ub["dim"]} == {"temperature", "temperature_difference"} else ""
        raise UnitError(f"차원이 다릅니다: {a}({ua['dim']}) → {b}({ub['dim']}){hint}")
    x = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(x)):
        raise UnitError("숫자가 아닌 값(NaN, 무한대)이 있어 변환하지 않습니다")
    with np.errstate(over="ignore", invalid="ignore"):
        si = x * ua["scale"] + ua.get("offset", 0.0)
    with np.errstate(over="ignore", invalid="ignore"):
        out = (si - ub.get("offset", 0.0)) / ub["scale"]
    if not np.all(np.isfinite(out)):
        raise UnitError("변환 결과가 유한하지 않습니다 (값이 너무 큽니다)")
    return float(out) if np.ndim(value) == 0 else out


_HEAD = re.compile(r"^(?P<name>.*?)\s*(?:\[(?P<u1>[^\]]+)\]|\((?P<u2>[^)]+)\))\s*$")


def split_header(cell: str) -> tuple[str, str | None]:
    """'온도 [degC]' 또는 '온도(degC)' → ('온도', 'degC'). 단위 표기가 없으면 (이름, None)."""
    m = _HEAD.match(cell.strip())
    if not m:
        return cell.strip(), None
    return m["name"].strip(), (m["u1"] or m["u2"]).strip()


def normalize_columns(names: list[str], columns: list[np.ndarray], target: dict[str, str]) -> tuple[list[str], list[np.ndarray], list[dict]]:
    """열 이름의 단위 표기를 읽어 target(열 이름 → 목표 단위)으로 바꾼다.

    target에 있는 열에 단위 표기가 없으면 추측하지 않고 거절한다. 반환의 세 번째는 열마다의 변환 기록.
    """
    out_names, out_cols, log = [], [], []
    for cell, col in zip(names, columns):
        name, unit = split_header(cell)
        want = target.get(name)
        if want is None:
            out_names.append(cell); out_cols.append(col); log.append({"column": cell, "converted": False})
            continue
        if unit is None:
            raise UnitError(f"'{name}' 열에 단위 표기가 없습니다. '{name} [{want}]'처럼 적거나 단위를 알려 주세요 (단위를 추측하지 않습니다)")
        out_names.append(f"{name} [{canonical(want)}]")
        out_cols.append(np.asarray(convert(col, unit, want)))
        log.append({"column": cell, "converted": True, "from": canonical(unit), "to": canonical(want)})
    return out_names, out_cols, log
