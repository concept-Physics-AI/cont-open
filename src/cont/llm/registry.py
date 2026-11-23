from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import yaml

from .providers import BUILTIN_TYPES

_TYPES: dict[str, Callable[..., Any]] = dict(BUILTIN_TYPES)
CONFIG_DIR = Path(os.environ.get("CONT_CONFIG_DIR", Path(__file__).resolve().parents[3] / "config"))


def register_type(type_name: str, factory: Callable[..., Any]) -> None:
    """Add a new provider type (e.g. an in-house model server) without touching callers."""
    _TYPES[type_name] = factory


def _load(config_dir: Path | None = None) -> dict[str, Any]:
    d = (config_dir or CONFIG_DIR) / "llm"
    merged: dict[str, Any] = {"default": None, "providers": {}}
    for f in (d / "providers.yaml", d / "providers.local.yaml"):
        if f.exists():
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            merged["default"] = data.get("default", merged["default"])
            merged["providers"].update(data.get("providers") or {})
    return merged


def list_providers(config_dir: Path | None = None) -> dict[str, Any]:
    return _load(config_dir)["providers"]


def get_provider(name: str | None = None, config_dir: Path | None = None):
    cfg = _load(config_dir)
    name = name or os.environ.get("CONT_LLM_PROVIDER") or cfg["default"]
    if not name or name not in cfg["providers"]:
        raise KeyError(f"LLM provider '{name}' not in config/llm/providers*.yaml")
    spec = dict(cfg["providers"][name])
    t = spec.pop("type")
    if t not in _TYPES:
        raise KeyError(f"provider type '{t}' not registered")
    return _TYPES[t](name=name, **spec)
