from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

MIN_SIDE, MAX_SIDE, STEP = 64, 2048, 8


class GenerationError(ValueError):
    """Bad request or a generator that could not produce an image."""


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    width: int = 1024
    height: int = 1024
    seed: int = 0
    steps: int | None = None  # None = the model's own default
    negative_prompt: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise GenerationError("prompt is empty")
        for side, v in (("width", self.width), ("height", self.height)):
            if isinstance(v, bool) or not isinstance(v, int) or not MIN_SIDE <= v <= MAX_SIDE or v % STEP:
                raise GenerationError(f"{side}={v!r}: need an int in [{MIN_SIDE}, {MAX_SIDE}], multiple of {STEP}")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise GenerationError(f"seed={self.seed!r}: need an int >= 0")
        if self.steps is not None and (isinstance(self.steps, bool) or not isinstance(self.steps, int)
                                       or not 1 <= self.steps <= 200):
            raise GenerationError(f"steps={self.steps!r}: need an int in [1, 200] or None")


@dataclass
class ImageResult:
    png: bytes
    width: int
    height: int
    model: str          # config name, e.g. "fake"
    weights: str        # what actually produced it (model id / file), for reproduction
    seed: int
    real: bool          # False = stand-in image (fake), never counts as real generation
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.png).hexdigest()

    def record(self) -> dict[str, Any]:
        """Everything needed to trace the image, without the bytes."""
        return {"model": self.model, "weights": self.weights, "seed": self.seed, "real": self.real,
                "width": self.width, "height": self.height, "sha256": self.sha256, "params": dict(self.params)}


class Generator(Protocol):
    name: str
    model: str
    real: bool

    def generate(self, request: ImageRequest) -> ImageResult: ...
