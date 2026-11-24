"""작은 완전연결 신경망과 시드 고정. torch가 필요하다."""
from __future__ import annotations

from cont.learn import require_torch
from cont.learn.config import TrainConfig


def set_seed(seed: int) -> None:
    """같은 프로세스·같은 환경에서 같은 결과가 나오도록 시드와 결정론 설정을 건다."""
    torch = require_torch()
    import random
    import numpy as np
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def build_mlp(in_dim: int, config: TrainConfig):
    """입력 in_dim, 출력 1인 MLP. 가중치는 config.seed로 초기화한다."""
    torch = require_torch()
    set_seed(config.seed)
    act = {"tanh": torch.nn.Tanh, "gelu": torch.nn.GELU, "sin": lambda: _Sin(torch)}[config.activation]
    dims = (in_dim, *config.hidden)
    layers = []
    for a, b in zip(dims[:-1], dims[1:]):
        layers += [torch.nn.Linear(a, b), act()]
    layers.append(torch.nn.Linear(dims[-1], 1))
    net = torch.nn.Sequential(*layers).to(getattr(torch, config.dtype))
    for m in net:
        if isinstance(m, torch.nn.Linear):
            torch.nn.init.xavier_normal_(m.weight)
            torch.nn.init.zeros_(m.bias)
    return net


def _Sin(torch):
    class Sin(torch.nn.Module):
        def forward(self, x):
            return torch.sin(x)
    return Sin()


def count_parameters(net) -> int:
    return sum(p.numel() for p in net.parameters())
