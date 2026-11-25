"""Real image models through diffusers (the only module that imports it).

Config (config/generation/models.yaml):
  sdxl:
    type: diffusers
    model: stabilityai/stable-diffusion-xl-base-1.0   # Hugging Face id, or a local folder (models.local.yaml)
    dtype: float16
    steps: 30
    guidance: 5.0
    variant: fp16           # download only the fp16 files (about half the size)
    offload: false          # true = move parts to CPU when VRAM is short (slower)
Weights are downloaded into the Hugging Face cache (set HF_HOME to keep it outside the repository).
Nothing heavy is imported until generate() is called, so a PC without diffusers still runs everything else.
"""
from __future__ import annotations

import io
from typing import Any, Callable

from .base import GenerationError, ImageRequest, ImageResult


def _default_loader(model: str, dtype: str, offload: bool, pipeline: str | None, variant: str | None = None) -> Any:
    try:
        import torch
        import diffusers
    except ImportError as e:  # pragma: no cover - depends on the PC
        raise GenerationError("diffusers/torch are not installed: pip install diffusers transformers accelerate") from e
    if not torch.cuda.is_available():
        raise GenerationError("no CUDA GPU: real image models are not run on CPU")
    td = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}.get(dtype)
    if td is None:
        raise GenerationError(f"dtype '{dtype}' not one of float16, bfloat16, float32")
    cls = getattr(diffusers, pipeline) if pipeline else diffusers.AutoPipelineForText2Image
    extra = {"variant": variant, "use_safetensors": True} if variant else {}
    pipe = cls.from_pretrained(model, torch_dtype=td, **extra)
    if offload:
        pipe.enable_model_cpu_offload()
    else:
        pipe.to("cuda")
    return pipe


def _default_generator(seed: int) -> Any:
    import torch
    return torch.Generator("cuda" if torch.cuda.is_available() else "cpu").manual_seed(seed)


class Diffusers:
    real = True

    def __init__(self, name: str, model: str, dtype: str = "float16", steps: int = 30, guidance: float = 5.0,
                 offload: bool = False, pipeline: str | None = None, variant: str | None = None,
                 loader: Callable[..., Any] | None = None,
                 generator_factory: Callable[[int], Any] | None = None, **_: Any):
        self.name, self.model, self.dtype, self.steps, self.guidance = name, model, dtype, int(steps), float(guidance)
        self.offload, self.pipeline, self._loader, self._pipe = bool(offload), pipeline, loader or _default_loader, None
        self.variant = variant
        self._gen = generator_factory or _default_generator

    def _get(self) -> Any:
        if self._pipe is None:  # loaded once, kept for the next request
            self._pipe = self._loader(self.model, self.dtype, self.offload, self.pipeline, self.variant)
        return self._pipe

    def generate(self, request: ImageRequest) -> ImageResult:
        pipe = self._get()
        steps = request.steps or self.steps
        gen = self._gen(request.seed)
        kw: dict[str, Any] = dict(prompt=request.prompt, width=request.width, height=request.height,
                                  num_inference_steps=steps, guidance_scale=self.guidance, generator=gen)
        if request.negative_prompt:
            kw["negative_prompt"] = request.negative_prompt
        out = pipe(**kw)
        images = getattr(out, "images", None)
        if not images:
            raise GenerationError(f"{self.name}: the model returned no image")
        img = images[0]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return ImageResult(png=buf.getvalue(), width=img.width, height=img.height, model=self.name,
                           weights=self.model, seed=request.seed, real=True,
                           params={"steps": steps, "guidance": self.guidance, "dtype": self.dtype,
                                   "offload": self.offload})
