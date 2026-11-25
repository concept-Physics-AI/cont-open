from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import yaml

from .providers import BUILTIN_TYPES

_TYPES: dict[str, Callable[..., Any]] = dict(BUILTIN_TYPES)
CONFIG_DIR = Path(os.environ.get("CONT_CONFIG_DIR", Path(__file__).resolve().parents[3] / "config"))


def register_type(type_name: str, factory: Callable[..., Any]) -> None:
    """Add a generator type (e.g. a diffusers model) without touching callers."""
    _TYPES[type_name] = factory


def _load(config_dir: Path | None = None) -> dict[str, Any]:
    d = (config_dir or CONFIG_DIR) / "generation"
    merged: dict[str, Any] = {"default": None, "purposes": {}, "models": {}}
    for f in (d / "models.yaml", d / "models.local.yaml"):
        if f.exists():
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            merged["default"] = data.get("default", merged["default"])
            merged["purposes"].update(data.get("purposes") or {})
            merged["models"].update(data.get("models") or {})
    return merged


def list_models(config_dir: Path | None = None) -> dict[str, Any]:
    return _load(config_dir)["models"]


def list_purposes(config_dir: Path | None = None) -> dict[str, str]:
    return _load(config_dir)["purposes"]


def get_generator(name: str | None = None, purpose: str | None = None, config_dir: Path | None = None):
    """Pick by name, else CONT_GEN_MODEL, else the model mapped to `purpose`, else the default."""
    cfg = _load(config_dir)
    if purpose is not None and purpose not in cfg["purposes"]:
        raise KeyError(f"purpose '{purpose}' not in config/generation/models*.yaml (known: {sorted(cfg['purposes'])})")
    name = name or os.environ.get("CONT_GEN_MODEL") or (cfg["purposes"][purpose] if purpose else None) or cfg["default"]
    if not name or name not in cfg["models"]:
        raise KeyError(f"generation model '{name}' not in config/generation/models*.yaml")
    spec = dict(cfg["models"][name])
    t = spec.pop("type")
    if t not in _TYPES:
        raise KeyError(f"generator type '{t}' not registered")
    return _TYPES[t](name=name, **spec)
