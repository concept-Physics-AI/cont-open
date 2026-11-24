"""문지기: 학습한 PINN을 학습 범위 안에서만 쓰고, 범위 밖이면 물리 선생(유한차분)으로 되돌린다.

문지기는 **범위만** 본다 (영역, 시간 구간, 학습한 열확산계수). PINN이 충분히 정확한지는 판단하지 않는다.
정확도 판정은 허용 오차 프로파일이 생길 때까지 하지 않는다 (CLAUDE.md 규칙 6). 범위 밖의 PINN 값은 만들지도, 보여 주지도 않는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cont.answer import (EVIDENCE_NONE, EVIDENCE_REFERENCE, STATUS_INPUT, STATUS_SIMULATED, VALIDATION_COMPARED, VALIDATION_NONE, Confidence,
                         PhysicsAnswer, Quantity)
from cont.learn import heat1d

REL_ALPHA = 1.0e-9      # 학습한 α와 같다고 보는 상대 차이 (부동소수점 비교용, 정확도 기준이 아니다)


@dataclass(frozen=True)
class GateDecision:
    use_pinn: bool
    in_domain: bool                 # x가 물리 영역 [0, 1] 안인가. 밖이면 물리 선생도 답할 수 없다
    reasons: tuple[str, ...] = ()   # 범위 밖인 이유 (비어 있으면 범위 안)


def decide_heat1d(problem: heat1d.Heat1DProblem, alpha: float, x: float, t: float) -> GateDecision:
    """한 점 (x, t)와 열확산계수 alpha가 이 PINN의 학습 범위 안인가."""
    if t < 0 or alpha <= 0 or not all(map(math.isfinite, (x, t, alpha))):
        raise ValueError("t must be non-negative, alpha positive, and all values finite")
    reasons = []
    in_domain = 0.0 <= x <= 1.0
    if not in_domain:
        reasons.append(f"x={x:g}가 물리 영역 [0, 1] 밖이다")
    if t > problem.horizon:
        reasons.append(f"t={t:g}가 학습한 시간 구간 [0, {problem.horizon:g}] 밖이다")
    if abs(alpha - problem.alpha) > REL_ALPHA * problem.alpha:
        reasons.append(f"α={alpha:g}가 학습한 값 {problem.alpha:g}과 다르다")
    return GateDecision(not reasons, in_domain, tuple(reasons))


def teacher_value(alpha: float, x: float, t: float, nx: int = 201) -> float:
    """물리 선생: 같은 문제(양 끝 0, 초기 sin(pi x))를 임의의 alpha와 시각 t까지 유한차분으로 푼 x에서의 값."""
    from cont.packs.heat import fd
    if t == 0.0:
        return math.sin(math.pi * x)
    steps = max(100, int(math.ceil(t * alpha * 400)))
    sol = fd.solve_1d(fd.Slab1D(1.0, alpha, 0.0, lambda xx: np.sin(math.pi * xx), t, t_right=0.0), nx, steps)
    return float(np.interp(x, sol.x, sol.temperature[-1]))


def query(trained: heat1d.Trained | None, points: list[tuple[float, float]], alpha: float | None = None, question: str = "",
          problem: heat1d.Heat1DProblem | None = None) -> PhysicsAnswer:
    """점 (x, t)마다 문지기를 거쳐 값을 낸다. 범위 안은 PINN과 물리 선생의 편차를 함께, 범위 밖은 물리 선생 값만 낸다.

    trained가 None이면(학습 도구가 없거나 학습하지 않음) 모든 점을 물리 선생이 답한다. 그때 문제 설정은 problem(기본 설정)이다.
    """
    if not points:
        raise ValueError("points must not be empty")
    p = trained.problem if trained is not None else (problem or heat1d.Heat1DProblem())
    a = p.alpha if alpha is None else alpha
    q: list[Quantity] = [Quantity("alpha", "열확산계수 α (무차원)", a, "-", None, None, STATUS_INPUT)]
    basis, used_pinn, any_value = [], 0, False
    for i, (x, t) in enumerate(points):
        d = decide_heat1d(p, a, x, t)
        if trained is None and d.use_pinn:
            d = GateDecision(False, d.in_domain, ("PINN 모형이 없다 (학습 도구가 설치되지 않았거나 학습하지 않았다)",))
        label = f"점 {i + 1}: x={x:g}, t={t:g}"
        if not d.in_domain:
            q.append(Quantity(f"u_{i}", f"{label}의 온도", None, "-", None, "물리 영역 밖이라 값을 내지 않는다"))
            basis.append(f"{label}: 물리 영역 밖. " + "; ".join(d.reasons))
            continue
        ref = teacher_value(a, x, t)
        any_value = True
        if d.use_pinn:
            used_pinn += 1
            v = float(heat1d.predict(trained, np.array([x]), np.array([t]))[0])
            q.append(Quantity(f"u_{i}", f"{label}의 온도", v, "-", None, "PINN (학습 범위 안)"))
            q.append(Quantity(f"deviation_{i}", f"{label}: PINN − 물리 선생", v - ref, "-", None, "편차만 보고한다"))
            basis.append(f"{label}: 학습 범위 안 → PINN 값. 물리 선생과의 편차를 함께 보고")
        else:
            q.append(Quantity(f"u_{i}", f"{label}의 온도", ref, "-", None, "물리 선생 (PINN 학습 범위 밖이라 되돌림)"))
            basis.append(f"{label}: 학습 범위 밖 → 물리 선생(유한차분)으로 되돌림. " + "; ".join(d.reasons))
    basis += ["문지기는 범위(영역, 시간 구간, 학습한 α)만 본다. PINN의 정확도는 판단하지 않는다",
              "범위 밖에서는 PINN 값을 만들지도 보여 주지도 않는다", "판정 없음: 편차는 값만 보고한다"]
    fell_back = any_value and used_pinn == 0
    valid = sum(1 for x, _ in points if 0.0 <= x <= 1.0)
    method = ("PINN (학습 범위 안)" if used_pinn == valid and used_pinn else
              "유한차분 (PINN 학습 범위 밖이라 되돌림)" if not used_pinn else "PINN (학습 범위 안) + 유한차분 되돌림 (범위 밖)")
    return PhysicsAnswer(
        status=STATUS_SIMULATED, question=question, quantities=tuple(q),
        method=method,
        basis=tuple(basis),
        confidence=Confidence("low" if used_pinn else "medium", "PINN 값은 학습 범위 안의 합성 문제에서만 확인했다. 되돌린 값은 기준 계산이다"),
        source="사람이 정한 질의 점. " + (f"학습 설정과 지문은 학습 기록에 있다: {trained.record.fingerprint()}" if trained is not None else "PINN 모형 없음"), uncertainty="",
        scope="무차원 1차원 열전도, 양 끝 0, 초기 sin(πx). PINN은 x∈[0,1], t∈[0,T], 학습한 α에서만 쓴다",
        failure_conditions=("PINN 학습이 수렴하지 않았을 때 (문지기는 이를 판단하지 않는다)", "경계·초기 조건이 학습한 것과 다를 때"),
        validation=VALIDATION_COMPARED if used_pinn else VALIDATION_NONE,
        evidence_level=EVIDENCE_NONE if used_pinn or not fell_back else EVIDENCE_REFERENCE,   # 가장 낮은 쪽을 따른다
        presentation=("table:quantities",),
        inputs={"alpha": a, "points": [list(pt) for pt in points], "trained": trained.record.fingerprint() if trained is not None else None},
    )
