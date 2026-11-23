"""진단 설정 읽기: 공통 모듈 정의(tables/)와 현장별 기준값(config/diagnosis/)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from cont.tolerance import CONFIG_DIR

TABLES = Path(__file__).parent / "tables"


@dataclass(frozen=True)
class ChangeType:
    role: str
    direction: str  # up | down
    key: str
    label: str


@dataclass(frozen=True)
class Module:
    name: str
    title: str
    roles: dict[str, dict[str, str]]
    conditions: dict[str, dict[str, str]]
    change_types: tuple[ChangeType, ...]
    keywords: tuple[str, ...] = ()

    def change_type(self, role: str, direction: str) -> ChangeType | None:
        for c in self.change_types:
            if c.role == role and c.direction == direction:
                return c
        return None


@dataclass(frozen=True)
class Settings:
    bins_per_condition: int
    min_samples_per_bin: int
    z_limit: float
    min_run: int
    merge_gap: int
    abrupt_jump_ratio: float
    min_training_samples: int
    trend_windows: int


def _read(p: Path) -> dict[str, Any]:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=None)
def load_module(name: str) -> Module:
    p = TABLES / f"{name}.yaml"
    if not p.exists():
        raise ValueError(f"diagnosis module '{name}' not found (available: {modules()})")
    d = _read(p)
    return Module(d["module"], d.get("title", name), d.get("roles", {}), d.get("conditions", {}),
                  tuple(ChangeType(**c) for c in d.get("change_types", [])),
                  tuple(str(k) for k in d.get("keywords", [])))


@dataclass(frozen=True)
class Special:
    name: str
    title: str
    rules: tuple[dict[str, Any], ...]
    stroke_zones: tuple[dict[str, Any], ...]


@lru_cache(maxsize=None)
def load_special(name: str) -> Special:
    p = TABLES / "special" / f"{name}.yaml"
    if not p.exists():
        raise ValueError(f"special diagnosis '{name}' not found (available: {specials()})")
    d = _read(p)
    return Special(d["special"], d.get("title", name), tuple(d.get("rules", [])), tuple(d.get("stroke_zones", [])))


def specials() -> list[str]:
    return sorted(p.stem for p in (TABLES / "special").glob("*.yaml"))


@lru_cache(maxsize=None)
def load_guidance() -> dict[str, dict[str, list[dict[str, str]]]]:
    """원인 후보와 점검 항목 표: 모듈 → 상태 변화 키 → [{cause, check}]."""
    return _read(TABLES / "guidance.yaml")


def modules() -> list[str]:
    return sorted(p.stem for p in TABLES.glob("*.yaml") if p.stem != "guidance")


def load_settings(name: str | None = None, config_dir: Path | None = None) -> Settings:
    d = (config_dir or CONFIG_DIR) / "diagnosis"
    merged = _read(d / "default.yaml")
    name = name or os.environ.get("CONT_DIAGNOSIS_PROFILE") or "default"
    if name != "default":
        for cand in (d / "profiles" / f"{name}.local.yaml", d / "profiles" / f"{name}.yaml"):
            if cand.exists():
                for section, values in _read(cand).items():
                    if isinstance(values, dict):
                        merged.setdefault(section, {}).update(values)
                break
        else:
            raise FileNotFoundError(f"diagnosis profile '{name}' not found in {d / 'profiles'}")
    b, t, sp = merged.get("baseline", {}), merged.get("detection", {}), merged.get("special", {})
    return Settings(int(b["bins_per_condition"]), int(b["min_samples_per_bin"]),
                    float(t["z_limit"]), int(t["min_run"]), int(t["merge_gap"]),
                    float(sp["abrupt_jump_ratio"]), int(sp["min_training_samples"]), int(merged.get("trend", {})["windows"]))
