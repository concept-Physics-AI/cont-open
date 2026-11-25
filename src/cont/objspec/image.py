"""공통 대상 명세 → 설명 이미지 요청 (Y9 ↔ 이미지).

명세의 부품 목록과 층 순서로 이미지 요청 문구를 만들고, 만든 이미지를 명세와 같은 부품 ID로 기록한다.
**부품 목록은 프롬프트에 적은 것이지 그림 픽셀에서 확인한 것이 아니다.** 그림이 실제로 그 층을 그렸는지는
사람이 보거나 이후 시각 검수가 확인한다(Representation.declared). 가짜(fake) 생성기 결과는 real=False로 남는다.
치수는 설명용이며 축척이 아니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cont.generation import Generator, ImageRequest, ImageResult

from .check import Representation
from .scene import CONFIG_DIR
from .spec import ObjectSpec, ObjectSpecError

_KEYS = ("lead", "tail", "negative", "roles", "groups", "stages")


def load_image_prompt(config_dir: Path | None = None) -> dict[str, Any]:
    f = (config_dir or CONFIG_DIR) / "objspec" / "image_prompt.yaml"
    with open(f, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    missing = [k for k in _KEYS if k not in cfg]
    if missing:
        raise ObjectSpecError(f"{f.name}에 {missing} 항목이 없습니다")
    return cfg


def layers_bottom_to_top(spec: ObjectSpec) -> list[str]:
    """부품 ID를 아래 면(z0) 순서로. 같으면 명세에 적은 순서."""
    order = {p.id: i for i, p in enumerate(spec.parts)}
    return [p.id for p in sorted(spec.parts, key=lambda p: (p.part.z0, order[p.id]))]


def image_prompt(spec: ObjectSpec, stage: int | str | None = None, config_dir: Path | None = None) -> tuple[str, str]:
    """(프롬프트, 부정 프롬프트). stage를 주면 그 공정 단계의 모습으로 쓴다."""
    cfg = load_image_prompt(config_dir)
    parts = []
    for pid in layers_bottom_to_top(spec):
        op = spec.part(pid)
        role = cfg["roles"].get(op.part.role, op.part.role)
        group = cfg["groups"].get(op.layer)
        parts.append(f"{role} ({group})" if group else role)
    text = [cfg["lead"], ", ".join(parts) + "."]
    if stage is not None:
        sid = spec.stage(stage).id
        if sid not in cfg["stages"]:
            raise ObjectSpecError(f"단계 '{sid}'의 이미지 문구가 {('image_prompt.yaml')}에 없습니다")
        text.append(cfg["stages"][sid] + ".")
    text.append(cfg["tail"])
    return " ".join(text), str(cfg["negative"])


def image_request(spec: ObjectSpec, stage: int | str | None = None, *, seed: int = 0, width: int = 1024,
                  height: int = 1024, steps: int | None = None, config_dir: Path | None = None) -> ImageRequest:
    prompt, negative = image_prompt(spec, stage, config_dir)
    return ImageRequest(prompt, width=width, height=height, seed=seed, steps=steps, negative_prompt=negative)


@dataclass
class SpecImage:
    result: ImageResult
    representation: Representation
    record: dict[str, Any]          # 이미지 기록 + 명세 연결(원본 바이트 제외)


def generate_image(spec: ObjectSpec, generator: Generator, stage: int | str | None = None, *, rep_id: str = "image",
                   seed: int = 0, width: int = 1024, height: int = 1024, steps: int | None = None,
                   config_dir: Path | None = None) -> SpecImage:
    """명세로 이미지를 만들고, 같은 부품 ID를 가리키는 표현과 기록을 함께 돌려준다."""
    req = image_request(spec, stage, seed=seed, width=width, height=height, steps=steps, config_dir=config_dir)
    res = generator.generate(req)
    sid = spec.stage(stage).id if stage is not None else None
    link = {"spec_version": spec.version, "parts": list(layers_bottom_to_top(spec)), "stage": sid,
            "dimension_status": spec.dimension_status, "parts_declared_by": "prompt"}
    res.params["object_spec"] = link
    rep = Representation(rep_id, "image", spec.version, tuple(layers_bottom_to_top(spec)),
                         tuple((p.id, p.part.name) for p in spec.parts))
    return SpecImage(res, rep, {**res.record(), "object_spec": link, "prompt": req.prompt})
