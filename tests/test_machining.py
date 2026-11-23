"""절삭가공 팩 슬라이스 1: 선삭의 절삭력 (키엔츨레 식)."""
import math

import pytest

from cont import packs
from cont.answer import NOT_REPORTED, STATUS_INPUT, STATUS_SIMULATED
from cont.packs.machining import TurningCut, answer
from cont.packs.machining import kienzle


def cut(**kw):
    base = dict(material="steel-x", diameter=60.0, cutting_speed=180.0, feed=0.25, depth=2.0, specific_cutting_force=2000.0, exponent=0.25)
    base.update(kw)
    return TurningCut(**base)


def test_force_power_and_speed_follow_the_formulas_by_hand():
    r = kienzle.calculate(cut(nose_radius=0.8, length=100.0, machine_efficiency=0.8))
    k_c = 2000.0 * 0.25 ** (-0.25)
    assert r.chip_thickness == pytest.approx(0.25) and r.chip_width == pytest.approx(2.0) and r.specific_force == pytest.approx(k_c)
    assert r.cutting_force == pytest.approx(k_c * 2.0 * 0.25)
    assert r.spindle_speed == pytest.approx(1000 * 180 / (math.pi * 60)) and r.torque == pytest.approx(r.cutting_force * 0.03)
    assert r.cutting_power == pytest.approx(r.cutting_force * 180 / 60000) and r.motor_power == pytest.approx(r.cutting_power / 0.8)
    assert r.cutting_power == pytest.approx(r.torque * r.spindle_speed * 2 * math.pi / 60000)       # 힘 x 속도 = 토크 x 각속도
    assert r.removal_rate == pytest.approx(2.0 * 0.25 * 180) and r.roughness_rt == pytest.approx(0.25**2 / (8 * 0.8) * 1000)
    assert r.time == pytest.approx(100.0 / (0.25 * r.spindle_speed) * 60)


def test_physical_trends_hold():
    base = kienzle.calculate(cut())
    assert kienzle.calculate(cut(depth=4.0)).cutting_force == pytest.approx(2 * base.cutting_force)             # 절입에 비례
    double_feed = kienzle.calculate(cut(feed=0.5))
    assert base.cutting_force < double_feed.cutting_force < 2 * base.cutting_force                             # 이송에는 비례보다 덜 는다
    assert double_feed.specific_force < base.specific_force                                                    # 칩이 두꺼우면 비절삭저항이 준다
    assert kienzle.calculate(cut(cutting_speed=360.0)).cutting_force == pytest.approx(base.cutting_force)       # 이 식에서는 속도와 무관
    assert kienzle.calculate(cut(cutting_speed=360.0)).cutting_power == pytest.approx(2 * base.cutting_power)
    slanted = kienzle.calculate(cut(edge_angle=45.0))
    assert slanted.chip_thickness < base.chip_thickness and slanted.chip_area == pytest.approx(base.chip_area)
    assert slanted.cutting_force > base.cutting_force                                                          # 같은 단면이라도 칩이 얇으면 힘이 는다


def test_pack_returns_the_common_format_with_status_and_no_verdict():
    a = packs.get("machining").solve({"cut": {"material": "C45", "diameter": 60.0, "cutting_speed": 180.0, "feed": 0.25, "depth": 2.0}})
    assert "machining" in packs.names() and a.status == STATUS_SIMULATED and a.status_of("specific_cutting_force_unit") == STATUS_INPUT
    assert a.value("cutting_force") > 0 and a.value("motor_power") is None and "machine_efficiency" in a.get("motor_power").note
    assert a.value("roughness_rt") is None and a.value("cutting_time") is None
    assert a.confidence.level == "low" and any("원문과 대조하지 않은 값" in b for b in a.basis)
    t = dict(a.trust())
    assert t["불확실성"] == NOT_REPORTED and t["물리잔차"] == NOT_REPORTED and t["값의 지위"].startswith("입력, 해석")
    text = " ".join(q.label + (q.note or "") for q in a.quantities)
    assert not any(w in text for w in ("합격", "불합격", "적합", "부적합"))
    assert answer(cut()).get("specific_cutting_force_unit").note == "직접 준 값"


def test_bad_input_is_refused_with_a_reason():
    with pytest.raises(ValueError, match="재료 표에 없습니다"):
        kienzle.calculate(TurningCut("unobtainium", 60.0, 180.0, 0.25, 2.0))
    for bad in (dict(feed=0.0), dict(depth=40.0), dict(edge_angle=0.0), dict(exponent=None), dict(exponent=1.2), dict(machine_efficiency=1.5),
                dict(nose_radius=-1.0)):
        with pytest.raises(ValueError):
            cut(**bad)
    with pytest.raises(ValueError, match="unknown cut fields"):
        TurningCut.from_dict({"material": "C45", "diameter": 60.0, "cutting_speed": 180.0, "feed": 0.25, "depth": 2.0, "colour": "red"})
    assert cut().modified(feed=0.3).feed == 0.3 and set(kienzle.material_names()) >= {"C45", "42CrMo4"}
