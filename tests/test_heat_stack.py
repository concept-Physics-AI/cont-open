"""Y6: 적층 1D 열응답 기준. 해석해·직렬 열저항·수렴 차수·에너지 보존, 지원 범위 밖 입력 거부, 실측 비교는 편차만 보고."""
from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import numpy as np
import pytest
import yaml

from cont.packs.heat import analytic
from cont.packs.heat.stack import (Layer, OutOfScope, Stack, check_scope, compare_response, convergence, scope, solve_stack,
                                   steady_state)

SI = dict(conductivity=150.0, density=2330.0, specific_heat=700.0)


def stack3(duration=2e-3, t_initial=350.0, **kw):
    return Stack((Layer("si", 5e-4, **SI), Layer("bond", 1e-6, 1.0, 2200.0, 800.0, interface_resistance=1e-7), Layer("si2", 5e-4, **SI)),
                 t_left=300.0, t_initial=t_initial, duration=duration, h_conv=500.0, t_inf=320.0, **kw)


def test_single_layer_matches_the_analytic_step_solution():
    L, al = 1e-3, 150.0 / (2330.0 * 700.0)
    s = Stack((Layer("si", L, **SI),), t_left=300.0, t_initial=400.0, duration=0.01, t_right=300.0)
    sol = solve_stack(s, cells=200, steps=400)
    ref = analytic.step_1d(sol.z, 0.01, L, al, 300.0, 400.0)
    assert np.abs(sol.temperature[-1] - ref).max() < 1e-4
    assert sol.energy_residual < 1e-10


def test_steady_state_matches_series_thermal_resistance():
    s = stack3(duration=5.0, t_initial=300.0)
    sol, ss = solve_stack(s), steady_state(s)
    assert abs(sol.flux_left_w_m2[-1] - ss["flux_w_m2"]) < 1e-6 * abs(ss["flux_w_m2"])
    r = 5e-4 / 150 * 2 + 1e-6 / 1.0 + 1e-7 + 1 / 500.0                  # 층 저항 + 계면 + 대류
    assert math.isclose(ss["flux_w_m2"], (300.0 - 320.0) / r, rel_tol=1e-12)


def test_interface_resistance_creates_the_expected_temperature_jump():
    """정상 상태에서 계면 양쪽 셀의 온도 차는 q × (접촉 저항 + 양쪽 반 셀의 전도 저항)과 같다."""
    rc = 1e-3
    base = stack3(duration=60.0, t_initial=300.0)                # 시간상수가 3초 안팎이라 60초면 정상 상태다
    big = dataclasses.replace(base, layers=(base.layers[0], dataclasses.replace(base.layers[1], interface_resistance=rc), base.layers[2]))
    sol = solve_stack(big)
    edge = sol.interface_z[1]                                   # 첫 층과 접합층 사이 계면
    i = int(np.searchsorted(sol.z, edge)) - 1                   # 계면 바로 왼쪽 셀
    q = steady_state(big)["flux_w_m2"]
    left_half = (edge - sol.z[i]) / 150.0                       # 왼쪽 셀 중심 → 계면: 규소 (k=150)
    right_half = (sol.z[i + 1] - edge) / 1.0                    # 계면 → 오른쪽 셀 중심: 접합층 (k=1)
    expected = abs(q) * (left_half + rc + right_half)
    got = abs(sol.temperature[-1][i + 1] - sol.temperature[-1][i])
    assert math.isclose(got, expected, rel_tol=1e-4)
    assert got > 10 * abs(solve_stack(base).temperature[-1][i + 1] - solve_stack(base).temperature[-1][i])    # 접촉 저항이 없을 때보다 훨씬 크다


def test_second_order_convergence_and_energy_balance():
    s = stack3()
    out = convergence(s, probe_z=7e-4)
    assert 1.8 < out["observed_order"] < 2.2                                       # 크랭크-니콜슨 + 중심차분은 2차
    assert solve_stack(s).energy_residual < 1e-9


def test_probe_interpolates_and_refuses_extrapolation():
    sol = solve_stack(stack3())
    assert sol.probe(5e-4).shape == sol.t.shape
    with pytest.raises(OutOfScope, match="외삽"):
        sol.probe(0.0)


@pytest.mark.parametrize("change,match", [
    (dict(t_initial=25.0), "켈빈"),                                               # 섭씨를 넣은 경우
    (dict(t_left=20.0), "켈빈"),
    (dict(duration=0.0), "지속 시간"),
    (dict(duration=float("nan")), "유한"),
    (dict(h_conv=1e9), "대류 계수"),
])
def test_out_of_scope_inputs_are_refused_before_any_calculation(change, match):
    s = dataclasses.replace(stack3(), **change)
    with pytest.raises(OutOfScope, match=match):
        solve_stack(s)


def test_layer_input_errors_are_refused():
    ok = stack3()
    mm = dataclasses.replace(ok, layers=(dataclasses.replace(ok.layers[0], thickness=0.5),) + ok.layers[1:])   # 0.5 m (mm를 m로 착각)
    with pytest.raises(OutOfScope, match="미터"):
        check_scope(mm)
    first = dataclasses.replace(ok, layers=(dataclasses.replace(ok.layers[0], interface_resistance=1e-6),) + ok.layers[1:])
    with pytest.raises(OutOfScope, match="첫 층"):
        check_scope(first)
    with pytest.raises(OutOfScope, match="층 수"):
        check_scope(dataclasses.replace(ok, layers=ok.layers * 4))
    both = dataclasses.replace(ok, t_right=300.0)
    with pytest.raises(OutOfScope, match="함께"):
        check_scope(both)
    neither = dataclasses.replace(ok, h_conv=None, t_inf=None)
    with pytest.raises(OutOfScope, match="중 하나"):
        check_scope(neither)


def test_grid_limits_are_enforced():
    s = stack3()
    with pytest.raises(OutOfScope, match="격자"):
        solve_stack(s, cells=5)
    with pytest.raises(OutOfScope, match="격자"):
        solve_stack(s, cells=10 ** 6)
    with pytest.raises(OutOfScope, match="걸음"):
        solve_stack(s, steps=10 ** 6)


def test_comparison_reports_deviation_only_and_never_judges():
    sol = solve_stack(stack3())
    sim = sol.probe(7e-4)
    meas_t = sol.t[::10]
    out = compare_response(sol.t, sim, meas_t, sim[::10] + 0.5)               # 실측이 0.5 K 높다
    assert out["judged"] is False and "pass" not in out and "ok" not in out
    assert math.isclose(out["bias_k"], -0.5, abs_tol=1e-9) and math.isclose(out["rmse_k"], 0.5, abs_tol=1e-9)
    assert out["points"] == len(meas_t) and out["points_outside_time_range"] == 0


def test_comparison_counts_points_outside_time_range_and_refuses_celsius():
    sol = solve_stack(stack3()); sim = sol.probe(7e-4)
    out = compare_response(sol.t, sim, [0.0, sol.t[-1] * 2], [sim[0], sim[0]])
    assert out["points"] == 1 and out["points_outside_time_range"] == 1
    with pytest.raises(OutOfScope, match="섭씨"):
        compare_response(sol.t, sim, [0.0], [27.0])
    with pytest.raises(OutOfScope, match="모두 계산한 시간 범위 밖"):
        compare_response(sol.t, sim, [10.0], [300.0])
    with pytest.raises(OutOfScope, match="길이"):
        compare_response(sol.t, sim, [0.0, 1e-3], [300.0])


def test_scope_config_values_are_numbers():
    b = scope()["bounds"]
    assert all(isinstance(x, (int, float)) for v in b.values() for x in v)


def test_every_yaml_config_number_is_parsed_as_a_number():
    """`1.0e5`처럼 지수 부호가 없는 표기는 YAML에서 문자열로 읽힌다. 설정에서 이런 값이 없는지 모든 yaml을 검사한다."""
    pat = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)$")
    bad = []
    def walk(x, where):
        if isinstance(x, dict):
            for k, v in x.items(): walk(v, f"{where}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x): walk(v, f"{where}[{i}]")
        elif isinstance(x, str) and pat.match(x.strip()):
            bad.append((where, x))
    for p in sorted((Path(__file__).resolve().parents[1] / "config").rglob("*.yaml")):
        walk(yaml.safe_load(p.read_text(encoding="utf-8")), p.name)
    assert not bad, f"숫자로 읽히지 않은 값(지수 표기에 부호가 필요합니다: 1.0e+5): {bad}"
