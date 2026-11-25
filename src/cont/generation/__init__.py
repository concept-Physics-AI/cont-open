"""One door for every image model.

Other modules call only:  get_generator(purpose="general").generate(ImageRequest(...))
Model list and purpose mapping live in config/generation/models.yaml (+ models.local.yaml, not in git).
Pick a model with CONT_GEN_MODEL=<name>. Weights stay outside the repository.
A result with real=False is a stand-in and never counts as a real generation.
"""
from .base import GenerationError, Generator, ImageRequest, ImageResult
from .registry import get_generator, list_models, list_purposes, register_type

__all__ = ["GenerationError", "Generator", "ImageRequest", "ImageResult",
           "get_generator", "list_models", "list_purposes", "register_type"]
