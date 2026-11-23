import numpy as np
import pytest

from cont import packs
from cont.packs.diagnosis import diagnose_equipment
from cont.packs.diagnosis import synthetic as syn
from cont.packs.diagnosis.demo import main as demo_main
from cont.packs.diagnosis.demo import synthetic_equipment, synthetic_special
from cont.packs.diagnosis.profile import load_special, specials
from cont.packs.diagnosis.special import assess_quality, diagnose_stroke, fit_quality, interpret
from cont.view import render_equipment, render_special


def spindle(current):
    return diagnose_equipment([{"name": "주축", "module": "drive", "normal": syn.drive(3000, seed=41), "current": current, "time": "t",
                                "signals": {"current": "current", "vibration": "vibration"},
                                "conditions": {"load": "load", "speed": "speed"}}], equipment="절삭 설비")


def test_same_common_change_means_different_things_by_how_it_starts():
    assert specials() == ["cutting", "extrusion", "press"] and len(load_special("press").stroke_zones) == 3
    drop = interpret("cutting", spindle(syn.inject(syn.drive(2000, seed=42), "current", 1400, 2000, -1.6)))
    (f,) = drop.findings
    assert (f.key, f.onset, f.start, f.system, f.signal) == ("tool_breakage", "abrupt", 1400.0, "주축", "current")
    wear = interpret("cutting", spindle(syn.inject(syn.drive(2000, seed=42), "current", 500, 2000, 1.2, ramp=True)))
    assert [(f.key, f.onset) for f in wear.findings] == [("tool_wear", "gradual")]       # 구간이 여러 개로 나뉘어도 한 건
    surge = interpret("cutting", spindle(syn.inject(syn.drive(2000, seed=42), "current", 800, 1200, 1.2)))
    assert [f.key for f in surge.findings] == ["overload"]
    a = drop.answer
    assert a.method.startswith("지식표") and a.confidence.level == "low" and a.value("findings") == 1
    assert any("공구 파손 의심" in b and "갑자기" in b for b in a.basis)


def test_interpretation_adds_nothing_when_the_rules_do_not_apply():
    quiet = interpret("cutting", spindle(syn.drive(2000, seed=43)))
    assert quiet.findings == () and any("이상 징후가 없어" in b for b in quiet.answer.basis)
    other = interpret("press", spindle(syn.inject(syn.drive(2000, seed=42), "current", 1400, 2000, -1.6)))   # 프레스 규칙에는 구동계 항목이 없다
    assert other.findings == () and any("규칙에 해당하는 것이 없음" in b for b in other.answer.basis)
    eq = synthetic_equipment()
    press = interpret("press", eq)
    assert [f.key for f in press.findings] == ["slow_stroke"]
    assert "이 공정에서의 뜻" in render_equipment(eq, findings=press.findings) and "이 공정에서의 뜻" not in render_equipment(eq)
    with pytest.raises(ValueError):
        interpret("welding", eq)


def test_stroke_curve_finds_the_zone_even_when_the_peak_load_is_unchanged():
    pos, normal = syn.stroke_curves(300, seed=51)
    _, cur = syn.stroke_curves(250, seed=52)
    assert diagnose_stroke(normal, cur, pos).answer.value("strokes_flagged") == 0
    changed = syn.inject_stroke(cur, pos, 150, 0.35, 0.5, 9.0)
    assert abs(changed.max(axis=1)[150:].mean() - cur.max(axis=1)[150:].mean()) < 0.5        # 최대 부하는 그대로
    d = diagnose_stroke(normal, changed, pos, unit="kN")
    assert d.answer.value("strokes_flagged") == 100 and d.answer.value("first_flagged_stroke") == 150
    assert not d.flagged[:150].any() and d.flagged[150:].all()
    ((name, iv),) = d.zones
    assert name == "성형 구간" and iv.direction == "up" and 0.34 < pos[iv.start] < 0.37 and 0.48 < pos[iv.end] < 0.51
    assert d.answer.value("zone1_deviation") == pytest.approx(9.0, abs=0.5)
    late = diagnose_stroke(normal, syn.inject_stroke(cur, pos, 0, 0.85, 0.95, -8.0), pos)
    assert [(n, iv.direction) for n, iv in late.zones] == [("하사점 부근", "down")]
    with pytest.raises(ValueError):
        diagnose_stroke(normal[:10], cur, pos)
    with pytest.raises(ValueError):
        diagnose_stroke(normal, cur[:, :50], pos)


def test_quality_model_predicts_thickness_and_says_when_it_is_guessing():
    feats = ["screw", "puller", "melt"]
    model = fit_quality(syn.extrusion(2000, seed=61), "thickness", feats)
    assert model.coef[1:] == pytest.approx([0.006, -0.02, -0.002], abs=0.001) and model.sigma == pytest.approx(0.008, rel=0.15)
    ok = assess_quality(model, syn.extrusion(1500, seed=63), (1.68, 1.82), time="t", measured="thickness", unit="mm")
    assert ok.answer.value("out_of_spec_intervals") == 0 and ok.answer.value("mean_absolute_error") < 0.01
    assert ok.answer.value("outside_training_range_fraction") < 0.02
    now = syn.extrusion(1500, seed=62)
    now["puller"][900:] -= 4.0                                  # 인취 속도가 느려져 두꺼워진다
    bad = assess_quality(model, now, (1.68, 1.82), time="t", unit="mm")
    a = bad.answer
    assert a.value("out_of_spec_intervals") >= 1 and a.value("first_out_of_spec_time") >= 900
    assert a.value("outside_training_range_fraction") == pytest.approx(0.4, abs=0.01)       # 학습 때 없던 운전 범위
    assert a.method.startswith("AI 대리모델") and any("믿기 어려움" in b for b in a.basis)
    assert all(iv.direction == "up" for iv in bad.chart.intervals)
    with pytest.raises(ValueError):
        fit_quality({k: v[:20] for k, v in syn.extrusion(100, seed=1).items()}, "thickness", feats)   # 정답 표본 부족
    with pytest.raises(ValueError):
        assess_quality(model, now, (1.8, 1.7))


def test_pack_routes_special_requests_and_the_special_screen_renders(tmp_path):
    p = packs.get("diagnosis")
    sys = [{"name": "주축", "module": "drive", "normal": syn.drive(3000, seed=41),
            "current": syn.inject(syn.drive(2000, seed=42), "current", 1400, 2000, -1.6),
            "signals": {"current": "current"}, "conditions": {"load": "load", "speed": "speed"}}]
    assert p.solve({"special": "cutting", "systems": sys}).get("finding1_tool_breakage").label == "주축: 공구 파손 의심"
    pos, normal = syn.stroke_curves(300, seed=51)
    assert p.solve({"task": "stroke", "normal": normal, "current": normal[:50], "position": pos}).value("strokes_checked") == 50
    q = p.solve({"task": "quality", "train": syn.extrusion(2000, seed=61), "current": syn.extrusion(500, seed=64),
                 "target": "thickness", "features": ["screw", "puller", "melt"], "spec": [1.68, 1.82]})
    assert 1.68 < q.value("predicted_mean") < 1.82
    secs = synthetic_special()
    page = render_special(secs)
    assert page.startswith("<!DOCTYPE html>") and page.count("<svg") == 4 and "http" not in page
    assert all(t in page for t in ("공구 파손 의심", "성형 구간", "규격 이탈 예측")) and "검증한 판정이 아닙니다" in page
    out = tmp_path / "sp.html"
    demo_main(["--special", "--out", str(out)])
    assert "설비 특화 이상진단" in out.read_text(encoding="utf-8")
