"""학습한 모형을 서비스에 내는 물리 팩 `heat_pinn`: 문지기를 거쳐 PINN 또는 물리 선생 값을 낸다.

입력: {"points": [[x, t], ...], "alpha": (선택), "profile": (선택, 학습 설정 이름)}.
PINN은 처음 부를 때 한 번 학습해 메모리에 둔다 (모델 파일을 만들지 않는다). torch가 없으면 모든 점을 물리 선생이 답한다.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from cont.answer import PhysicsAnswer
from cont.learn import available, gate, heat1d, load_profile
from cont.packs import register

MAX_POINTS = 20
DEFAULT_PROFILE = "heat1d_bench"


@lru_cache(maxsize=2)
def trained_model(profile: str = DEFAULT_PROFILE) -> heat1d.Trained:
    return heat1d.train(heat1d.Heat1DProblem(), load_profile(profile))


class HeatPinnPack:
    name = "heat_pinn"

    def solve(self, inputs: Mapping[str, Any], question: str = "") -> PhysicsAnswer:
        raw = inputs.get("points")
        if not isinstance(raw, (list, tuple)) or not raw or len(raw) > MAX_POINTS:
            raise ValueError(f"points는 [x, t] 쌍이 1~{MAX_POINTS}개 든 목록이어야 합니다")
        try:
            points = [(float(x), float(t)) for x, t in raw]
            alpha = None if inputs.get("alpha") is None else float(inputs["alpha"])
        except (TypeError, ValueError) as e:
            raise ValueError("points와 alpha는 숫자여야 합니다") from e
        for x, t in points:                                  # 학습(수십 초)을 시작하기 전에 입력부터 거른다
            gate.decide_heat1d(heat1d.Heat1DProblem(), alpha if alpha is not None else 1.0, x, t)
        profile = str(inputs.get("profile", DEFAULT_PROFILE))
        trained = trained_model(profile) if available() else None
        return gate.query(trained, points, alpha, question)


PACK = register(HeatPinnPack())
