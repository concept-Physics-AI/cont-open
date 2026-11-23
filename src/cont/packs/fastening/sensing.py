"""현장 계측 추천: 이 조인트의 체결력을 알아내려면 무엇을 어떻게 달아야 하는가.

계측 방법과 연결은 표(tables/sensing.yaml)에 있고, 여기서는 **이 조인트에서 나오는 신호의 크기**를 계산해 방법마다 붙인다.
볼트가 얼마나 늘어나는지, 초음파 왕복 시간이 얼마나 변하는지, 볼트 축의 변형률이 얼마인지, 로드셀이 받아야 할 힘이 얼마인지.
그리고 "토크만으로 조일 때보다 나아지려면 늘어남을 얼마나 정밀하게 재야 하는가"를 낸다.

추천의 순서는 규칙으로 정한다 (근거는 각 항목의 why에 적는다). 제품 이름, 가격, 제품별 정확도는 다루지 않는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from cont.packs.fastening import standards, vdi2230
from cont.packs.fastening.estimate import settings as estimate_settings
from cont.packs.fastening.joint import BoltedJoint, LoadCase

TABLES = Path(__file__).parent / "tables"


@lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    with open(TABLES / "sensing.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class Signal:
    label: str
    value: float | None
    unit: str
    note: str = ""


@dataclass(frozen=True)
class Option:
    key: str
    rank: int
    stage: str                       # 어느 단계에 쓰는가
    label: str
    measures: str
    why: str                         # 이 조인트에서 이 순서인 이유
    signals: tuple[Signal, ...]      # 이 조인트에서 나오는 신호의 크기
    hardware: tuple[str, ...]
    chain: tuple[str, ...]           # 연결 순서
    protocol: str
    into_cont: str
    cautions: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    summary: str
    torque_only_spread: float | None         # 토크만으로 조일 때 체결력의 흩어짐 (± 비율). 마찰 범위가 없으면 None
    elongation: float                        # 예상 볼트 늘어남 (mm)
    needed_elongation_uncertainty: float | None   # 토크만일 때보다 나아지려면 필요한 늘어남의 표준 불확도 (mm)
    options: tuple[Option, ...]
    limits: tuple[str, ...]


def plan(joint: BoltedJoint, load: LoadCase) -> Plan:
    t = table()
    c = t["constants"]
    r = vdi2230.calculate(joint, load)
    s = estimate_settings()
    k, model_u = s["coverage_factor"], s["bolt_resilience_relative_uncertainty"]

    elong = r.delta_s * r.preload
    spread = (r.preload_max - r.preload_min) / (2 * r.preload) if load.friction_range else None
    needed = None
    if spread is not None and spread / k > model_u:
        needed = elong * math.sqrt((spread / k) ** 2 - model_u**2)
    length = joint.clamp_length + joint.thread.head_height + joint.thread.nut_height + standards.shape_constant("thread_protrusion_pitches") * joint.p
    v = float(c["sound_speed_longitudinal"]) * 1000.0                       # mm/s
    tof_base = 2 * length / v * 1e6                                         # 왕복 시간 (us)
    tof_geom = 2 * elong / v * 1e9                                          # 늘어난 길이만의 몫 (ns)
    tof_total = tof_geom / (1 - float(c["tof_stress_share"]))               # 응력에 따른 음속 감소를 더한 전체 (ns)
    strain = r.preload / (vdi2230.vdi_constant("youngs_modulus_bolt") * math.pi * joint.d**2 / 4) * 1e6
    f_top = r.preload_max

    def signals_for(key: str) -> tuple[Signal, ...]:
        if key == "tool_controller":
            return (Signal("조임 토크", load.tightening_torque, "N·m"),
                    Signal("이 토크에서 체결력의 흩어짐", None if spread is None else spread * 100, "%",
                           "마찰 범위를 주지 않아 계산하지 않음" if spread is None else f"마찰계수 {load.friction_range[0]:g} ~ {load.friction_range[1]:g}일 때 ±"))
        if key == "ultrasonic":
            return (Signal("볼트 늘어남", elong, "mm"),
                    Signal("초음파 왕복 시간 (조이기 전)", tof_base, "us", f"볼트 길이 약 {length:.0f} mm"),
                    Signal("조인 뒤 왕복 시간의 증가", tof_total, "ns", f"그중 늘어난 길이의 몫 {tof_geom:.0f} ns, 나머지는 응력으로 음속이 줄어든 몫"),
                    Signal("토크만일 때보다 나아지려면 재야 할 시간 정밀도", None if needed is None else needed / elong * tof_total, "ns",
                           "" if needed is not None else "계산하지 않음"))
        if key == "load_washer":
            return (Signal("로드셀이 받는 힘 (대표)", r.preload / 1000, "kN"),
                    Signal("받을 수 있어야 하는 힘 (마찰이 가장 작을 때)", f_top / 1000, "kN", "정격은 이 값 이상이어야 한다"),
                    Signal("안지름", joint.hole, "mm", "볼트 구멍 지름 이상"))
        return (Signal("볼트 축의 변형률", strain, "ue", f"축 지름 {joint.d:g} mm 기준"),
                Signal("체결력 1 kN당 변형률", strain / (r.preload / 1000), "ue/kN"))

    small = f"왕복 시간의 변화가 {tof_total:.0f} ns로 작다. 작은 볼트에서 정확도가 제한된다는 보고가 있으므로 벤치에서 먼저 확인한다"
    order = (
        ("tool_controller", "1단계: 지금 라인에서", "볼트와 조인트에 아무것도 더하지 않는다. 공구 제어기가 이미 재고 있는 값을 받기만 하면 된다. "
         + ("다만 체결력은 여전히 ±%.0f%% 흩어진다" % (spread * 100) if spread is not None else "다만 토크만으로는 체결력의 흩어짐을 알 수 없다")),
        ("load_washer", "2단계: 검증 벤치에서", "체결력을 직접 잰다. 기준값이 되어 다른 방법(초음파, 계산식)을 맞추는 데 쓴다. "
         "볼트 컴플라이언스 계산값이 실제와 얼마나 다른지도 여기서 정해진다 (지금은 5%로 잠정)"),
        ("ultrasonic", "3단계: 라인에서 표본으로", "여기 든 방법 가운데 양산 조인트에 부품을 더하지 않고 체결력을 추정하는 방법이다. " + small),
        ("strain_gauge_bolt", "필요할 때: 기준 볼트로", "정밀하게 잴 수 있지만 볼트 가운데에 구멍을 내야 해서 큰 볼트에 주로 쓴다. "
         f"{joint.size}에 맞는 게이지 볼트를 구할 수 있는지부터 확인한다. 구할 수 있으면 벤치의 기준 볼트로 쓴다"),
    )
    options = []
    for rank, (key, stage, why) in enumerate(order, start=1):
        m = t["methods"][key]
        options.append(Option(key, rank, stage, m["label"], m["measures"], why, signals_for(key), tuple(m["hardware"]), tuple(m["chain"]),
                              m["protocol"], m["into_cont"], tuple(m["cautions"]), tuple(m["sources"])))
    head = (f"이 조인트({joint.size}, 체결 길이 {joint.clamp_length:g} mm, {load.tightening_torque:g} N·m)에서 볼트는 약 {elong * 1000:.0f} µm 늘어난다. ")
    if needed is not None:
        head += (f"토크만으로 조이면 체결력이 ±{spread * 100:.0f}% 흩어지므로, 늘어남을 표준 불확도 {needed * 1000:.1f} µm보다 정밀하게 재야 토크만일 때보다 나아진다.")
    elif spread is not None:
        head += (f"토크만일 때의 흩어짐(±{spread * 100:.0f}%)이 볼트 컴플라이언스 계산값의 불확도({model_u * 100:g}%, 잠정)보다 작아, 늘어남을 재도 지금 모형으로는 나아지지 않는다.")
    return Plan(head, spread, elong, needed, tuple(options), (
        "제품 이름, 가격, 제품별 정확도는 다루지 않는다. 확인하지 않은 값을 싣지 않기 위해서다",
        "신호의 크기는 VDI 2230 식으로 계산한 값이다 (해석, 검증 전). 실제 계측기를 고를 때는 제조사 사양과 맞춰 본다",
        f"필요한 정밀도는 볼트 컴플라이언스 계산값의 불확도 {model_u * 100:g}%(잠정)와 범위 계수 {k:g}에 좌우된다",
        f"음속 {c['sound_speed_longitudinal']} m/s는 강의 교과서 값이다. 볼트 재료로 교정해야 한다",
        "공구 제어기, 초음파 계측기, 데이터 수집 장치에서 값을 받아 오는 연결 코드는 아직 없다",
    ))
