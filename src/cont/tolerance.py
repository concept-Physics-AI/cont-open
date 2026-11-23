"""Tolerance profiles: limits come from config, never from code.

Default profile has limit=None for every quantity -> deviation is reported, no pass/fail.
Selection: CONT_TOLERANCE_PROFILE=<name>  (profiles/<name>.local.yaml wins over profiles/<name>.yaml)
Override one value: CONT_TOL__<QUANTITY>__LIMIT=<number>
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(os.environ.get("CONT_CONFIG_DIR", Path(__file__).resolve().parents[2] / "config"))


@dataclass(frozen=True)
class Tolerance:
    quantity: str
    mode: str  # relative | absolute | range_match | rank
    limit: float | None
    unit: str | None = None


@dataclass(frozen=True)
class Check:
    quantity: str
    deviation: float | None
    limit: float | None
    passed: bool | None  # None = no limit set -> report only


def _read(p: Path) -> dict[str, Any]:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _profile_file(name: str, tol_dir: Path) -> Path:
    for cand in (tol_dir / "profiles" / f"{name}.local.yaml", tol_dir / "profiles" / f"{name}.yaml"):
        if cand.exists():
            return cand
    raise FileNotFoundError(f"tolerance profile '{name}' not found in {tol_dir / 'profiles'}")


def load_profile(name: str | None = None, config_dir: Path | None = None) -> dict[str, Tolerance]:
    tol_dir = (config_dir or CONFIG_DIR) / "tolerances"
    base = _read(tol_dir / "default.yaml").get("quantities", {})
    merged = {k: dict(v) for k, v in base.items()}
    name = name or os.environ.get("CONT_TOLERANCE_PROFILE") or "default"
    if name != "default":
        for k, v in (_read(_profile_file(name, tol_dir)).get("quantities") or {}).items():
            merged.setdefault(k, {}).update(v or {})
    for k, v in merged.items():
        env = os.environ.get(f"CONT_TOL__{k.upper()}__LIMIT")
        if env is not None:
            v["limit"] = None if env.strip().lower() in ("", "none", "null") else float(env)
    return {
        k: Tolerance(k, v.get("mode", "relative"), v.get("limit"), v.get("unit"))
        for k, v in merged.items()
    }


def check(tol: Tolerance, value: float, reference: float) -> Check:
    """Deviation for relative/absolute modes. Other modes are judged by their own pack code."""
    if tol.mode == "relative":
        dev = abs(value - reference) / abs(reference) if reference else None
    elif tol.mode == "absolute":
        dev = abs(value - reference)
    else:
        raise ValueError(f"mode '{tol.mode}' is not a scalar comparison")
    passed = None if tol.limit is None or dev is None else dev <= tol.limit
    return Check(tol.quantity, dev, tol.limit, passed)
