import math

import numpy as np
import pytest

from cont import packs
from cont.answer import EVIDENCE_REFERENCE, STATUS_INPUT, STATUS_SIMULATED, VALIDATION_COMPARED
from cont.packs.heat import analytic, fd

L, AL = 0.1, 1.0e-4


def slab(duration=20.0):
    return fd.Slab1D(L, AL, 300.0, lambda x: analytic.sine_1d(x, 0.0, L, AL, 300.0, 50.0), duration, t_right=300.0)


def rms(nx, steps):
    s = fd.solve_1d(slab(), nx, steps)
    return float(np.sqrt(np.mean((s.temperature[-1] - analytic.sine_1d(s.x, 20.0, L, AL, 300.0, 50.0)) ** 2)))


def test_1d_matches_analytic_and_converges_second_order():
    e1, e2, e3 = rms(21, 40), rms(41, 80), rms(81, 160)
    assert e3 < e2 < e1
    assert 1.8 < math.log2(e1 / e2) < 2.2 and 1.8 < math.log2(e2 / e3) < 2.2


def test_1d_boundaries_hold_and_state_is_monotone_decay():
    s = fd.solve_1d(slab(), 41, 40)
    assert np.all(s.temperature[:, 0] == 300.0) and np.all(s.temperature[:, -1] == 300.0)
    assert np.all(np.diff(s.temperature.max(axis=1)) < 0)


def test_1d_convective_end_approaches_linear_steady_state():
    p = fd.Slab1D(L, AL, 400.0, lambda x: np.full_like(x, 400.0), 4000.0, conductivity=50.0, h_conv=500.0, t_inf=300.0)
    s = fd.solve_1d(p, 41, 400)
    ref = analytic.convective_steady_1d(s.x, L, 50.0, 500.0, 400.0, 300.0)
    assert float(np.max(np.abs(s.temperature[-1] - ref))) < 0.05


def test_2d_matches_analytic():
    errs = []
    for n, st in ((11, 20), (21, 40)):
        p = fd.Plate2D(0.1, 0.05, AL, 300.0, lambda X, Y: analytic.sine_2d(X, Y, 0.0, 0.1, 0.05, AL, 300.0, 40.0), 2.0)
        s = fd.solve_2d(p, n, n, st)
        gx, gy = np.meshgrid(s.x, s.y)
        errs.append(float(np.sqrt(np.mean((s.temperature[-1] - analytic.sine_2d(gx, gy, 2.0, 0.1, 0.05, AL, 300.0, 40.0)) ** 2))))
    assert errs[1] < errs[0] / 3


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        fd.Slab1D(0.0, AL, 300.0, lambda x: x, 1.0, t_right=300.0)
    with pytest.raises(ValueError):
        fd.Slab1D(L, AL, 300.0, lambda x: x, 1.0)
    with pytest.raises(ValueError):
        fd.solve_1d(slab(), 3, 10)


@pytest.mark.parametrize("case", ["sine_1d", "step_1d", "sine_2d"])
def test_pack_reports_deviation_without_judging(case):
    a = packs.get("heat").solve({"case": case})
    assert "heat" in packs.names()
    assert a.status == STATUS_SIMULATED and a.validation == VALIDATION_COMPARED and a.evidence_level == EVIDENCE_REFERENCE
    assert a.status_of("diffusivity") == STATUS_INPUT and a.status_of("deviation_rms") == STATUS_SIMULATED
    dev = next(q for q in a.quantities if q.key == "deviation_rms")
    assert dev.value is not None and dev.value < 0.1       # 느슨한 건전성 한계. 제품 허용 오차가 아니다
    order = next(q for q in a.quantities if q.key == "grid_order")
    assert 1.5 < order.value < 2.5
    assert any("판정 없음" in b for b in a.basis)
    assert a.residuals and a.residuals[0].key == "analytic_deviation"


def test_pack_2d_has_field_and_is_deterministic():
    a = packs.get("heat").solve({"case": "sine_2d"})
    assert len(a.fields) == 1 and a.fields[0].key == "temperature"
    assert a.to_dict() == packs.get("heat").solve({"case": "sine_2d"}).to_dict()


def test_unknown_case_is_rejected():
    with pytest.raises(ValueError):
        packs.get("heat").solve({"case": "nope"})
