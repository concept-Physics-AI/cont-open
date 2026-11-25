"""Built-in generator types.

fake: offline stand-in. Draws a deterministic gradient PNG from the request; marked real=False.
Real image models (diffusers) are added as new types by register_type - see config/generation/README.md.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from typing import Any

from .base import ImageRequest, ImageResult


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def png_bytes(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Small valid RGB PNG (diagonal gradient around rgb). Standard library only."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            d = (x + y) * 64 // (width + height)
            rows += bytes(min(255, c // 2 + d + 64) for c in rgb)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + _chunk(b"IEND", b"")


class Fake:
    real = False

    def __init__(self, name: str, model: str = "fake", max_side: int = 256, **_: Any):
        self.name, self.model, self.max_side = name, model, int(max_side)

    def generate(self, request: ImageRequest) -> ImageResult:
        # the stand-in is drawn small so tests stay fast; the size asked for is kept in the record
        w, h = min(request.width, self.max_side), min(request.height, self.max_side)
        digest = hashlib.sha256(f"{request.prompt}|{request.negative_prompt}|{request.seed}|{request.steps}".encode()).digest()
        return ImageResult(png=png_bytes(w, h, (digest[0], digest[1], digest[2])), width=w, height=h,
                           model=self.name, weights="fake", seed=request.seed, real=False,
                           params={"asked_width": request.width, "asked_height": request.height, "steps": request.steps})


from .diffusers_gen import Diffusers  # noqa: E402  (imports diffusers only when generating)

BUILTIN_TYPES = {"fake": Fake, "diffusers": Diffusers}
