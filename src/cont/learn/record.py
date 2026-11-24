"""학습 기록: 같은 결과를 다시 만들 수 있도록 설정, 시드, 손실 이력, 환경을 남긴다. 모델 파일은 남기지 않는다."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from cont.learn.config import TrainConfig


@dataclass(frozen=True)
class TrainingRecord:
    problem: str                                   # 예: "heat_1d_sine"
    config: TrainConfig
    loss_history: tuple[float, ...] = ()           # 에포크마다 총 손실 (간격은 loss_every)
    loss_every: int = 1
    final_losses: dict[str, float] = field(default_factory=dict)   # 마지막 에포크의 항별 손실 (pde, boundary, initial)
    torch_version: str = ""
    device: str = "cpu"
    parameters: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"problem": self.problem, "config": self.config.to_dict(), "loss_history": list(self.loss_history),
                "loss_every": self.loss_every, "final_losses": dict(self.final_losses), "torch_version": self.torch_version,
                "device": self.device, "parameters": self.parameters}

    def fingerprint(self) -> str:
        """재현 점검용 지문. 환경(torch 버전)은 빼고 문제·설정·손실 이력만 본다."""
        d = self.to_dict()
        d.pop("torch_version")
        return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
