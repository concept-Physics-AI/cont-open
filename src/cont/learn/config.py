"""학습 설정. 값은 코드에 박지 않고 profiles/*.yaml 에 둔다 (규칙 5). torch 없이도 가져올 수 있다."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROFILES = Path(__file__).parent / "profiles"


@dataclass(frozen=True)
class TrainConfig:
    seed: int = 0
    hidden: tuple[int, ...] = (32, 32, 32)      # 은닉층 너비
    activation: str = "tanh"
    epochs: int = 2000
    learning_rate: float = 1.0e-3
    n_interior: int = 2000                      # 방정식 잔차를 보는 내부 점 수
    n_boundary: int = 200                       # 경계 조건 점 수
    n_initial: int = 200                        # 초기 조건 점 수
    weights: dict[str, float] = field(default_factory=lambda: {"pde": 1.0, "boundary": 1.0, "initial": 1.0})
    dtype: str = "float64"

    def __post_init__(self) -> None:
        if self.activation not in ("tanh", "sin", "gelu"):
            raise ValueError("activation must be one of tanh, sin, gelu")
        if self.epochs < 1 or self.learning_rate <= 0 or not self.hidden or min(self.hidden) < 1:
            raise ValueError("epochs, learning_rate and hidden must be positive")
        if min(self.n_interior, self.n_boundary, self.n_initial) < 1:
            raise ValueError("point counts must be positive")
        if self.dtype not in ("float32", "float64"):
            raise ValueError("dtype must be float32 or float64")
        if set(self.weights) != {"pde", "boundary", "initial"} or min(self.weights.values()) < 0:
            raise ValueError("weights must have non-negative pde, boundary and initial")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hidden"] = list(self.hidden)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrainConfig":
        d = dict(d)
        if "hidden" in d:
            d["hidden"] = tuple(d["hidden"])
        return cls(**d)


def load_profile(name: str) -> TrainConfig:
    """profiles/<name>.yaml 의 학습 설정."""
    path = PROFILES / f"{name}.yaml"
    if not path.is_file():
        raise KeyError(f"unknown learning profile '{name}' (available: {sorted(p.stem for p in PROFILES.glob('*.yaml'))})")
    return TrainConfig.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
