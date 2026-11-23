"""현장 계측 추천: 방법과 연결은 표에서, 신호의 크기는 이 조인트의 계산에서 나온다."""
import math
from dataclasses import replace

import pytest

from cont.dialogue.serve_fastening import example, scripted
from cont.packs.fastening import vdi2230
from cont.packs.fastening.estimate import settings
from cont.packs.fastening.sensing import plan, table
from cont.view.fastening_live import render_live, sensing_html


def sig(option, label):
    return next(s for s in option.signals if s.label == label)


def test_signals_are_computed_from_this_joint_not_quoted():
    j, l = example()
    r = vdi2230.calculate(j, l)
    p = plan(j, l)
    assert [o.key for o in p.options] == ["tool_controller", "load_washer", "ultrasonic", "strain_gauge_bolt"] and [o.rank for o in p.options] == [1, 2, 3, 4]
    tool, washer, ultra, gauge = p.options
    assert p.elongation == pytest.approx(r.delta_s * r.preload) and sig(ultra, "볼트 늘어남").value == pytest.approx(p.elongation)
    assert p.torque_only_spread == pytest.approx((r.preload_max - r.preload_min) / (2 * r.preload))
    assert sig(tool, "이 토크에서 체결력의 흩어짐").value == pytest.approx(p.torque_only_spread * 100)
    assert sig(washer, "받을 수 있어야 하는 힘 (마찰이 가장 작을 때)").value == pytest.approx(r.preload_max / 1000) and sig(washer, "안지름").value == j.hole
    total = sig(ultra, "조인 뒤 왕복 시간의 증가").value
    geometric = 2 * p.elongation / 5.9e6 * 1e9
    assert total == pytest.approx(geometric * 3, rel=1e-3)                       # 늘어난 길이의 몫이 3분의 1
    assert sig(gauge, "볼트 축의 변형률").value == pytest.approx(r.preload / (205000 * math.pi * 25) * 1e6, rel=0.02)
    bigger = plan(j, replace(l, tightening_torque=70.0))
    assert bigger.elongation > p.elongation and sig(bigger.options[2], "조인 뒤 왕복 시간의 증가").value > total


def test_needed_precision_is_what_it_takes_to_beat_torque_alone():
    j, l = example()
    p = plan(j, l)
    s = settings()
    rel = math.hypot(p.needed_elongation_uncertainty / p.elongation, s["bolt_resilience_relative_uncertainty"])
    assert s["coverage_factor"] * rel == pytest.approx(p.torque_only_spread)      # 딱 그 정밀도면 범위가 토크만일 때와 같다
    assert f"{p.needed_elongation_uncertainty * 1000:.1f} um" in p.summary and "117 um" in p.summary
    tight = plan(j, replace(l, friction_range=(0.118, 0.122)))                    # 마찰이 거의 안 흩어지면 재도 나아지지 않는다
    assert tight.needed_elongation_uncertainty is None and "나아지지 않는다" in tight.summary
    none = plan(j, replace(l, friction_range=None))
    assert none.torque_only_spread is None and none.needed_elongation_uncertainty is None
    assert sig(none.options[0], "이 토크에서 체결력의 흩어짐").value is None


def test_every_method_says_how_to_connect_it_and_cites_its_sources_and_nothing_is_a_product_pitch():
    j, l = example()
    p = plan(j, l)
    for o in p.options:
        assert o.chain[-1] == "ConT" and len(o.chain) >= 4 and o.hardware and o.cautions and o.sources and o.into_cont and o.why
    assert "4545" in p.options[0].protocol and "MID 0061" in p.options[0].protocol
    assert "아직 없음" in p.options[1].into_cont and "이미 있는 기능" in p.options[2].into_cont
    assert any("제품 이름, 가격" in x for x in p.limits) and any("연결 코드는 아직 없다" in x for x in p.limits)
    text = " ".join(str(v) for m in table()["methods"].values() for v in m.values())
    import re
    assert not re.search(r"\d\s*(만\s*)?원|USD|\$|€", text)                       # 가격을 싣지 않는다
    assert table()["constants"]["tof_stress_share_source"].startswith("US 4,899,591")


def test_the_live_screen_has_a_sensing_section_that_follows_the_joint():
    j, l = example()
    h = sensing_html(j, l)
    assert all(x in h for x in ("1단계: 지금 라인에서", "2단계: 검증 벤치에서", "3단계: 라인에서 표본으로", "Open Protocol", 'class="chain"'))
    states = scripted(("M12로 바꿔줘",))
    assert states[0]["sensing"] != states[1]["sensing"] and "M12" in states[1]["sensing"]
    page = render_live(states)
    assert 'id="acc-sensing"' in page and "현장에서 재려면: 센서와 연결" in page and page.count('<details class="acc"') == 5
