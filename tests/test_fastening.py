import math

import pytest

from cont import packs
from cont.packs.fastening import BoltedJoint, LoadCase, Plate, answer, standards, vdi2230

STEEL = 205000.0


def joint(**kw):
    base = dict(
        size="M10", property_class="10.9",
        plate_head=Plate(15.0, STEEL), plate_nut=Plate(15.0, STEEL), outer_diameter=40.0,
    )
    base.update(kw)
    return BoltedJoint(**base)


def load(**kw):
    base = dict(tightening_torque=50.0, friction_thread=0.12, friction_head=0.12)
    base.update(kw)
    return LoadCase(**base)


def test_thread_geometry_m10_matches_iso_values():
    g = vdi2230.thread_geometry(10.0, 1.5)
    assert g.d2 == pytest.approx(9.026, abs=1e-3)
    assert g.d3 == pytest.approx(8.160, abs=1e-3)
    assert g.a_s == pytest.approx(58.0, abs=0.05)  # ISO 898-1: 58.0 mm^2


def test_stress_areas_of_all_sizes_match_iso_898():
    iso = {"M6": 20.1, "M8": 36.6, "M10": 58.0, "M12": 84.3, "M16": 157.0, "M20": 245.0, "M24": 353.0}
    for name, area in iso.items():
        t = standards.thread_size(name)
        assert vdi2230.thread_geometry(t.d, t.pitch_coarse).a_s == pytest.approx(area, rel=0.003)


def test_torque_and_preload_are_inverse():
    args = (1.5, 9.026, 14.63, 11.0, 0.12, 0.10)
    f = vdi2230.preload_from_torque(50_000.0, *args)
    assert vdi2230.torque_from_preload(f, *args) == pytest.approx(50_000.0)
    # 마찰이 크면 같은 토크에서 체결력이 작다
    assert vdi2230.preload_from_torque(50_000.0, 1.5, 9.026, 14.63, 11.0, 0.16, 0.16) < f


def test_plate_resilience_equals_vdi_closed_form_for_wide_plate():
    j = joint(outer_diameter=200.0)  # 원뿔이 바깥지름에 닿지 않는다
    d_w, d_h, l_k, e = j.bearing_diameter, j.hole, j.clamp_length, STEEL
    tan_phi = vdi2230.cone_angle_tan(l_k, d_w, j.outer_diameter)
    closed = 2 * math.log((d_w + d_h) * (d_w + l_k * tan_phi - d_h) / ((d_w - d_h) * (d_w + l_k * tan_phi + d_h))) / (
        e * math.pi * d_h * tan_phi
    )
    assert vdi2230.plate_resilience(j) == pytest.approx(closed, rel=1e-12)


def test_plate_resilience_equals_vdi_closed_form_for_cone_plus_sleeve():
    j = joint(outer_diameter=20.0)  # d_W < D_A < D_A,Gr
    d_w, d_h, l_k, d_a, e = j.bearing_diameter, j.hole, j.clamp_length, j.outer_diameter, STEEL
    tan_phi = vdi2230.cone_angle_tan(l_k, d_w, d_a)
    assert d_w < d_a < d_w + l_k * tan_phi
    closed = (
        2 / (d_h * tan_phi) * math.log((d_w + d_h) * (d_a - d_h) / ((d_w - d_h) * (d_a + d_h)))
        + 4 / (d_a**2 - d_h**2) * (l_k - (d_a - d_w) / tan_phi)
    ) / (e * math.pi)
    assert vdi2230.plate_resilience(j) == pytest.approx(closed, rel=1e-12)


def test_plate_resilience_sleeve_only_when_plate_is_not_wider_than_head():
    j = joint(outer_diameter=14.0)
    expected = 4 * j.clamp_length / (STEEL * math.pi * (14.0**2 - j.hole**2))
    assert vdi2230.plate_resilience(j) == pytest.approx(expected, rel=1e-12)


def test_softer_plate_is_more_compliant_and_takes_less_of_the_load():
    steel = vdi2230.calculate(joint(), load(axial_load_max=5000.0))
    alu_plate = Plate(15.0, 70000.0)
    alu = vdi2230.calculate(joint(plate_head=alu_plate, plate_nut=alu_plate), load(axial_load_max=5000.0))
    assert alu.delta_p == pytest.approx(steel.delta_p * STEEL / 70000.0, rel=1e-9)
    assert alu.load_factor > steel.load_factor
    mixed = vdi2230.calculate(joint(plate_head=alu_plate), load())
    assert steel.delta_p < mixed.delta_p < alu.delta_p


def test_axial_load_is_split_between_bolt_and_plates():
    r = vdi2230.calculate(joint(), load(axial_load_max=8000.0, load_introduction_factor=0.5))
    assert 0 < r.load_factor < 1
    assert r.bolt_extra_load_max + r.plate_relief_max == pytest.approx(8000.0)
    assert r.bolt_load_max == pytest.approx(r.preload_max + r.bolt_extra_load_max)
    assert r.residual_clamp_min == pytest.approx(r.preload_min - r.plate_relief_max)
    # 벌어짐 시작 하중에서는 잔류 체결력이 0이 된다
    at_opening = vdi2230.calculate(joint(), load(axial_load_max=r.opening_load, load_introduction_factor=0.5))
    assert at_opening.residual_clamp_min == pytest.approx(0.0, abs=1e-6)
    assert at_opening.safety_opening == pytest.approx(1.0)


def test_friction_range_gives_preload_range_and_embedding_reduces_clamp():
    r = vdi2230.calculate(joint(), load(friction_range=(0.10, 0.14), embedding=0.011))
    assert r.preload_min < r.preload < r.preload_max
    assert r.preload_loss_embedding == pytest.approx(0.011 / (r.delta_s + r.delta_p))
    assert r.residual_clamp_min == pytest.approx(r.preload_min - r.preload_loss_embedding)


def test_bolt_stress_slip_pressure_and_fatigue():
    j = joint(plate_head=Plate(15.0, STEEL, limit_pressure=700.0))
    r = vdi2230.calculate(j, load(axial_load_max=6000.0, axial_load_min=1000.0, transverse_load=2000.0,
                                  friction_interface=0.15))
    g = r.geometry
    assert r.stress_assembly > r.preload_max / g.a_s  # 비틀림이 더해진다
    assert r.safety_yield == pytest.approx(r.yield_strength / r.stress_working)
    assert r.safety_slip == pytest.approx(r.residual_clamp_min * 0.15 / 2000.0)
    assert r.pressure_max == pytest.approx(r.bolt_load_max / (math.pi / 4 * (14.63**2 - 11.0**2)))
    assert r.safety_pressure_head == pytest.approx(700.0 / r.pressure_max)
    assert r.safety_pressure_nut is None  # 한계 면압을 주지 않은 판은 판정 재료가 없다
    assert r.stress_amplitude == pytest.approx(r.load_factor * 5000.0 / (2 * g.a_s))
    assert r.fatigue_limit == pytest.approx(0.85 * (150 / 10 + 45))
    assert r.safety_fatigue == pytest.approx(r.fatigue_limit / r.stress_amplitude)


def test_parametric_change_recalculates_from_standard_data():
    j10 = joint()
    j12 = j10.modified(size="M12", plate_head_thickness=20.0)
    assert (j12.p, j12.hole, j12.bearing_diameter) == (1.75, 13.5, 16.63)
    assert j12.clamp_length == 35.0 and j10.clamp_length == 30.0
    assert vdi2230.calculate(j12, load()).preload < vdi2230.calculate(j10, load()).preload  # 같은 토크, 더 굵은 볼트
    assert joint(property_class="8.8").yield_strength == 640.0
    assert joint(size="M20", property_class="8.8").yield_strength == 660.0


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        joint(size="M11")
    with pytest.raises(ValueError):
        joint(property_class="9.9")
    with pytest.raises(ValueError):
        joint(hole_diameter=9.5)
    with pytest.raises(ValueError):
        joint(shank_length=40.0)
    with pytest.raises(ValueError):
        load(friction_range=(0.2, 0.1))
    with pytest.raises(ValueError):
        BoltedJoint.from_dict({"size": "M10", "colour": "red"})


def test_pack_returns_common_answer_format_without_judgement():
    pack = packs.get("fastening")
    assert "fastening" in packs.names()
    ans = pack.solve(
        {
            "joint": {
                "size": "M10", "property_class": "10.9", "outer_diameter": 40.0,
                "plate_head": {"thickness": 15.0, "youngs_modulus": STEEL},
                "plate_nut": {"thickness": 15.0, "youngs_modulus": STEEL},
            },
            "load": {"tightening_torque": 50.0, "friction_thread": 0.12, "friction_head": 0.12,
                     "friction_range": [0.10, 0.14]},
        },
        question="M10 10.9 볼트를 50 N·m로 조이면 체결력은?",
    )
    direct = answer(joint(), load(friction_range=(0.10, 0.14)))
    preload = ans.get("preload")
    assert preload.value == pytest.approx(direct.value("preload"))
    assert preload.unit == "N" and preload.expected_range[0] < preload.value < preload.expected_range[1]
    assert ans.method.startswith("해석식") and ans.confidence.level == "medium" and ans.retention == "ephemeral"
    assert ans.value("safety_slip") is None and ans.get("safety_slip").note  # 계산 못 한 값은 이유를 적는다
    assert ans.value("thread_shear_margin") is None
    d = ans.to_dict()
    assert set(d) == {"question", "quantities", "method", "basis", "confidence", "presentation", "retention", "inputs",
                      "status", "source", "uncertainty", "residuals", "validation", "scope", "failure_conditions", "fields"}
    assert all({"key", "label", "value", "unit", "expected_range", "note", "status", "evidence", "identifiability", "identifiability_basis"} == set(x) for x in d["quantities"])
    assert not any(k in x for x in d["quantities"] for k in ("passed", "verdict"))  # 판정 항목이 없다
    again = pack.solve(d["inputs"])  # 보관된 입력으로 같은 답을 다시 만든다
    assert again.value("preload") == pytest.approx(preload.value)
