"""체결된 판의 응력 분포 (수치해석)와 그것을 그린 물리 이미지."""
import math
from dataclasses import replace

import numpy as np
import pytest

from cont.answer import STATUS_INPUT, STATUS_SIMULATED, Confidence, PhysicsAnswer
from cont.dialogue.serve_fastening import example, scripted
from cont.packs.fastening import vdi2230
from cont.packs.fastening.field import settings, solve, stress_field
from cont.view.fastening_live import render_live, stress_image
from cont.view.field_image import NO_IMAGE, colour, field_image


def test_the_field_carries_the_preload_at_every_height_and_reports_its_own_residual():
    j, l = example()
    a = stress_field(j, l)
    preload = vdi2230.calculate(j, l).preload
    assert a.status == STATUS_SIMULATED and a.status_of("preload") == STATUS_INPUT and a.method.startswith("수치해석")
    f = a.field("plate_axial_compression")
    s = settings()
    assert len(f.x) == s["radial_cells_under_head"] + s["radial_cells_outside"] and len(f.y) == s["axial_cells"] and f.unit == "MPa"
    area = math.pi * ((j.outer_diameter / 2) ** 2 - (j.hole / 2) ** 2)
    assert a.value("interface_mean_pressure") * area == pytest.approx(preload, rel=0.01)       # 판 사이 면이 체결력을 그대로 받는다
    (res,) = a.residuals
    assert res.key == "axial_balance" and 0 < res.value < 0.01 * preload                        # 0은 아니지만 체결력의 1% 안
    assert a.value("peak_compression") > a.value("interface_peak_pressure") > a.value("interface_mean_pressure") > 0
    assert j.bearing_diameter / 2 < a.value("pressed_radius") <= j.outer_diameter / 2
    assert a.uncertainty.startswith("반영하지 않음") and a.confidence.level == "low" and any("붙어 있다" in b for b in a.basis)
    assert a.to_dict()["fields"][1]["key"] == "plate_von_mises"


def test_stress_scales_with_preload_and_equal_plates_give_a_field_symmetric_about_the_interface():
    j, _ = example()
    sol1, v1 = solve(j, 10000.0)
    sol2, v2 = solve(j, 30000.0)
    assert np.allclose(sol2.stress, 3 * sol1.stress) and v2["resilience"] == pytest.approx(v1["resilience"])
    comp = -sol1.stress[..., 1]
    assert np.allclose(comp, comp[::-1], rtol=1e-6, atol=1e-6)
    soft = replace(j, plate_head=replace(j.plate_head, youngs_modulus=70000.0))                 # 머리 쪽만 알루미늄
    assert solve(soft, 10000.0)[1]["resilience"] > v1["resilience"]


def test_numerical_and_vdi_plate_resilience_are_compared_without_a_verdict():
    j, l = example()
    a = stress_field(j, l)
    fem, vdi, dev = a.value("plate_resilience_fem"), a.value("plate_resilience_vdi"), a.value("plate_resilience_deviation")
    assert vdi == pytest.approx(vdi2230.calculate(j, l).delta_p) and dev == pytest.approx((fem - vdi) / vdi * 100)
    assert 0.5 * vdi < fem < 2.0 * vdi and a.get("plate_resilience_deviation").note.startswith("판정 없음")
    text = " ".join(q.label + (q.note or "") for q in a.quantities)
    assert not any(w in text for w in ("합격", "불합격", "적합", "부적합"))


def test_the_physics_image_is_drawn_only_from_a_field_and_says_what_it_is():
    j, l = example()
    a = stress_field(j, l)
    svg = field_image(a, "plate_axial_compression", lines=((15.0, "판 사이 면"),), marks=((5.5, 8.0, 30.0, "머리 좌면"),))
    assert svg.startswith("<svg") and "해석 · 수치해석 (축대칭 유한요소, 선형 탄성) · 검증 전" in svg
    assert 'href="data:image/png;base64,' in svg and 'data-card="' in svg and "<polygon" not in svg      # 칸 모양이 아니라 부드러운 한 장의 그림
    assert all(t in svg for t in ("볼트 자리 (계산에 넣지 않음)", "판 사이 면", "머리 좌면", "0보다 작은 곳"))
    empty = PhysicsAnswer("q", (), "해석식", (), Confidence("low", "r"))
    assert field_image(empty, "plate_axial_compression") == NO_IMAGE and field_image(a, "no_such_field") == NO_IMAGE
    assert colour(-1.0) == colour(0.0) != colour(1.0) == colour(2.0)


def test_the_live_screen_shows_the_stress_distribution_as_its_own_view():
    j, l = example()
    cap = stress_image(j, l)
    assert "판 컴플라이언스는 VDI 식보다" in cap and "평형 잔차" in cap and "판정은 하지 않습니다" in cap
    states = scripted(("토크 75로 올려줘",))
    assert states[0]["views"]["field"] != states[1]["views"]["field"]
    page = render_live(states)
    assert 'data-v="field"' in page and 'id="pane-field"' in page and ".fieldimg" in page
