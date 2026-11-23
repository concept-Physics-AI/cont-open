"""숨은 물리의 복원: 볼트 늘어남 관측 → 체결력과 마찰계수 추정 (역문제).

체결력은 직접 잴 수 없다. 조임 토크에서 계산하면 마찰을 가정해야 하고, 마찰은 조일 때마다 다르다.
볼트가 늘어난 길이는 잴 수 있다 (초음파, 마이크로미터). 볼트는 스프링이므로 늘어남에서 체결력을 거꾸로 구할 수 있다.

    체결력 F = 늘어남 / 볼트 컴플라이언스 delta_S
    마찰계수 mu = (조임 토크 / F - 0.16 P) / (0.58 d2 + D_Km / 2)      (나사면과 좌면의 마찰이 같다고 볼 때)

결과의 지위는 "추정"이다. 불확실성(측정의 흩어짐, 계기의 불확도, 볼트 컴플라이언스 계산값의 불확도)을 범위로 함께 내고,
토크 모형이 예상한 체결력과 얼마나 어긋나는지를 물리잔차로 낸다. 판정은 하지 않는다.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, replace

import yaml

from cont.answer import IDENT_NONE, IDENT_OK, IDENT_WEAK, STATUS_ESTIMATED, STATUS_INPUT, STATUS_OBSERVED, STATUS_SIMULATED, Confidence, PhysicsAnswer, Quantity, Residual
from cont.packs.fastening import vdi2230
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.tolerance import CONFIG_DIR

SCOPE = "조인 직후 탄성 범위 안의 볼트. 늘어남은 조이기 전과 후를 같은 온도에서 잰 차이"
FAILS = ("볼트가 항복했을 때 (늘어남이 체결력에 비례하지 않는다)", "조이기 전후의 온도가 다를 때", "늘어남을 볼트 전체가 아닌 일부 길이에서 쟀을 때",
         "나사면과 좌면의 마찰이 크게 다를 때 (마찰계수 추정만 해당)")


@dataclass(frozen=True)
class ElongationMeasurement:
    """볼트 늘어남 관측. values: 같은 볼트를 여러 번 잰 값 (mm). instrument_uncertainty: 계기의 표준 불확도 (mm)."""

    values: tuple[float, ...]
    instrument_uncertainty: float
    source: str = ""                 # 무엇으로 쟀는지 (예: "초음파 축력계"). 합성 데이터면 그렇게 적는다

    def __post_init__(self) -> None:
        if not self.values or any(v <= 0 for v in self.values):
            raise ValueError("elongation values must be positive")
        if self.instrument_uncertainty < 0:
            raise ValueError("instrument_uncertainty must not be negative")

    @property
    def mean(self) -> float:
        return statistics.fmean(self.values)

    @property
    def standard_uncertainty(self) -> float:
        """평균의 표준 불확도: 반복 측정의 흩어짐과 계기의 불확도를 합친다."""
        scatter = statistics.stdev(self.values) / math.sqrt(len(self.values)) if len(self.values) > 1 else 0.0
        return math.hypot(scatter, self.instrument_uncertainty)


def settings() -> dict[str, float]:
    with open(CONFIG_DIR / "fastening" / "default.yaml", encoding="utf-8") as f:
        s = (yaml.safe_load(f) or {})["estimate"]
    return {"bolt_resilience_relative_uncertainty": float(s["bolt_resilience_relative_uncertainty"]), "coverage_factor": float(s["coverage_factor"]),
            "weak_identifiability_relative_uncertainty": float(s["weak_identifiability_relative_uncertainty"])}


@dataclass(frozen=True)
class Estimate:
    answer: PhysicsAnswer
    preload: float
    preload_range: tuple[float, float]
    friction: float
    friction_range: tuple[float, float]
    within_model_range: bool         # 추정한 체결력이 토크 모형의 마찰 범위가 예상한 체결력 범위 안에 있는가 (사실 보고, 판정 아님)


def estimate(joint: BoltedJoint, load: LoadCase, measured: ElongationMeasurement, question: str = "") -> Estimate:
    s = settings()
    k = s["coverage_factor"]
    model = vdi2230.calculate(joint, load)
    g = model.geometry
    delta_s = model.delta_s
    elong, u_elong = measured.mean, measured.standard_uncertainty
    preload = elong / delta_s
    rel = math.hypot(u_elong / elong, s["bolt_resilience_relative_uncertainty"])
    u_preload = preload * rel
    f_lo, f_hi = max(preload - k * u_preload, 0.0), preload + k * u_preload

    torque = load.tightening_torque * 1000.0
    arm = 0.58 * g.d2 + (joint.bearing_diameter + joint.hole) / 4

    def mu_of(force: float) -> float:
        return (torque / force - 0.16 * g.p) / arm

    mu = mu_of(preload)
    mu_lo, mu_hi = (mu_of(f_hi), mu_of(f_lo)) if f_lo > 0 else (mu_of(f_hi), float("inf"))     # 체결력이 클수록 마찰은 작다
    physical = mu > 0 and mu_lo > 0

    def derived(friction: float) -> vdi2230.Result:
        return vdi2230.calculate(joint, replace(load, friction_thread=friction, friction_head=friction, friction_range=None))

    def q(key: str, label: str, value: float | None, unit: str, rng: tuple[float, float] | None = None, note: str | None = None,
          status: str | None = None, evidence: tuple[str, ...] = (), ident: tuple[str, str] | None = None) -> Quantity:
        return Quantity(key, label, value, unit, rng, note, status, evidence, ident[0] if ident else None, ident[1] if ident else None)

    def ident_of(relative: float) -> tuple[str, str]:
        level = IDENT_WEAK if relative > s["weak_identifiability_relative_uncertainty"] else IDENT_OK
        return level, f"상대 표준 불확도 {relative * 100:.1f}%"

    from_elongation = ("bolt_elongation", "bolt_resilience")
    from_both = ("bolt_elongation", "bolt_resilience", "tightening_torque")

    quantities = [
        q("bolt_elongation", "볼트 늘어남 (관측, 평균)", elong, "mm", (elong - k * u_elong, elong + k * u_elong),
          f"{len(measured.values)}회 측정. 표준 불확도 {u_elong:.2g} mm", STATUS_OBSERVED),
        q("tightening_torque", "조임 토크", load.tightening_torque, "N·m", status=STATUS_INPUT),
        q("bolt_resilience", "볼트 컴플라이언스 delta_S (계산값)", delta_s, "mm/N", status=STATUS_SIMULATED),
        q("preload_estimated", "체결력 (늘어남에서 추정)", preload, "N", (f_lo, f_hi), evidence=from_elongation, ident=ident_of(rel)),
        q("preload_model", "체결력 (토크 모형, 대표 마찰)", model.preload, "N", (model.preload_min, model.preload_max),
          "비교용. 마찰을 가정해 토크에서 계산한 값", STATUS_SIMULATED),
    ]
    if physical:
        mid, lo, hi = derived(mu), derived(mu_hi), derived(mu_lo)       # 마찰이 크면 체결력이 작다: lo = 체결력이 작은 쪽
        mu_ident = ident_of((mu_hi - mu_lo) / (2 * k) / mu) if math.isfinite(mu_hi) else (IDENT_WEAK, "범위의 위쪽 끝이 정해지지 않는다")
        quantities += [
            q("friction_estimated", "마찰계수 (추정, 나사면 = 좌면)", mu, "-", (mu_lo, mu_hi), evidence=from_both, ident=mu_ident),
            q("residual_clamp_estimated", "남는 체결력 (추정한 체결력으로)", mid.residual_clamp_min, "N", (lo.residual_clamp_min, hi.residual_clamp_min), evidence=from_both, ident=mu_ident),
            q("bolt_equivalent_stress_estimated", "운전 시 볼트 등가응력 (추정한 체결력으로)", mid.stress_working, "MPa", (lo.stress_working, hi.stress_working), evidence=from_both, ident=mu_ident),
            q("safety_yield_estimated", "항복 안전율 (추정한 체결력으로)", mid.safety_yield, "-", (hi.safety_yield, lo.safety_yield), evidence=from_both, ident=mu_ident),
        ]
    else:
        quantities.append(q("friction_estimated", "마찰계수 (추정, 나사면 = 좌면)", None, "-",
                            note="늘어남과 토크가 서로 맞지 않아 계산하지 않는다 (추정한 체결력이 마찰이 0일 때 그 토크로 낼 수 있는 값보다 크다)",
                            evidence=from_both, ident=(IDENT_NONE, "늘어남과 토크가 서로 맞지 않는다")))
    within = model.preload_min <= preload <= model.preload_max
    gap = preload - model.preload
    where = "토크 모형이 마찰 범위로 예상한 체결력 범위 안이다" if within else "토크 모형이 마찰 범위로 예상한 체결력 범위 밖이다"
    if load.friction_range is None:
        where = "토크 모형에 마찰 범위를 주지 않아 범위와 견줄 수 없다"
    answer = PhysicsAnswer(
        status=STATUS_ESTIMATED, question=question, quantities=tuple(quantities),
        method="역문제 복원 (볼트 늘어남 = 체결력 x 볼트 컴플라이언스, VDI 2230 Part 1의 식)",
        basis=(
            "체결력 = 관측한 늘어남 / 볼트 컴플라이언스 (VDI 2230 Part 1의 delta_S 계산식)",
            "마찰계수 = (조임 토크 / 체결력 - 0.16 P) / (0.58 d2 + D_Km / 2)",
            f"볼트 {joint.size} x 피치 {g.p} mm, 체결 길이 {joint.clamp_length:g} mm",
            "가정: 관측한 늘어남은 볼트 컴플라이언스 계산이 담은 변형(머리, 축, 나사, 너트 물림) 전체와 같다",
            "가정: 나사면과 좌면의 마찰계수가 같다 (마찰계수 추정에만 쓴다)",
            f"가정: 볼트 컴플라이언스 계산값의 상대 불확도 {s['bolt_resilience_relative_uncertainty']:g} (표준에서 온 값이 아니라 잠정으로 둔 값)",
            "판정 없음: 추정값과 범위만 보고한다",
        ),
        confidence=Confidence("low", "합성 데이터로 식을 되돌려 확인했을 뿐이고, 실제 측정(초음파 축력, 변형률 게이지 볼트)과 대조하지 않았다"),
        source=f"관측: 볼트 늘어남 {len(measured.values)}회" + (f" ({measured.source})" if measured.source else "") + ". 입력: 치수, 조임 토크",
        uncertainty=(f"범위는 표준 불확도의 {k:g}배다. 반복 측정의 흩어짐, 계기의 불확도 {measured.instrument_uncertainty:g} mm, "
                     f"볼트 컴플라이언스 계산값의 불확도 {s['bolt_resilience_relative_uncertainty'] * 100:g}%를 합쳤다. 체결력의 상대 불확도 {rel * 100:.1f}%"),
        residuals=(Residual("observation_model_gap", "관측에서 추정한 체결력 - 토크 모형의 체결력 (대표 마찰)", gap, "N", where),),
        scope=SCOPE, failure_conditions=FAILS,
        presentation=("table:quantities",),
        inputs={"joint": asdict(joint), "load": asdict(load), "measured": asdict(measured)},
    )
    return Estimate(answer, preload, (f_lo, f_hi), mu if physical else float("nan"), (mu_lo, mu_hi) if physical else (float("nan"), float("nan")), within)


def synthetic_elongations(joint: BoltedJoint, load: LoadCase, true_friction: float, noise: float, count: int, seed: int = 0) -> tuple[float, ...]:
    """확인용 합성 관측: 참 마찰계수로 조였다고 보고 늘어남을 만든 뒤 잡음을 더한다. 실제 측정이 아니다."""
    import random
    truth = vdi2230.calculate(joint, replace(load, friction_thread=true_friction, friction_head=true_friction, friction_range=None))
    rng = random.Random(seed)
    return tuple(truth.delta_s * truth.preload + rng.gauss(0.0, noise) for _ in range(count))
