"""학습(C7): PyTorch 호출, PINN, 학습 설정·시드·기록.

`torch`는 이 패키지 안에서만 가져온다. 설치하지 않아도 이 패키지를 가져올 수 있고,
학습을 실제로 돌리는 함수만 `require_torch()`에서 막힌다. 모델 파일은 커밋하지 않고 설정과 시드로 다시 만든다.
"""
from __future__ import annotations

import importlib.util

from cont.learn.config import TrainConfig, load_profile
from cont.learn.record import TrainingRecord


def available() -> bool:
    """torch가 설치돼 있는가 (가져오지는 않는다)."""
    return importlib.util.find_spec("torch") is not None


def require_torch():
    """torch를 가져와 돌려준다. 없으면 설치 방법을 알리며 멈춘다."""
    if not available():
        raise RuntimeError("PyTorch가 설치돼 있지 않습니다. `pip install -e .[learn]`로 설치하세요")
    import torch
    return torch


__all__ = ["TrainConfig", "TrainingRecord", "available", "require_torch", "load_profile"]
