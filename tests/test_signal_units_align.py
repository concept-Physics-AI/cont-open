"""R07 단위 정규화, R08 시간 정렬."""
import math

import numpy as np
import pytest

from cont.signal.align import AlignError, check_time, compare_before_after, regularize
from cont.signal.units import UnitError, convert, normalize_columns, split_header


def test_temperature_offsets():
    assert math.isclose(convert(0.0, "degC", "K"), 273.15)
    assert math.isclose(convert(300.0, "K", "degC"), 26.85, abs_tol=1e-9)
    assert math.isclose(convert(32.0, "degF", "degC"), 0.0, abs_tol=1e-9)
    assert math.isclose(convert(212.0, "°F", "℃"), 100.0, abs_tol=1e-9)


def test_scale_conversions_and_round_trip():
    assert math.isclose(convert(1.5, "MPa", "Pa"), 1.5e6)
    assert math.isclose(convert(25.0, "mm", "m"), 0.025)
    assert math.isclose(convert(1.0, "bar", "kPa"), 100.0)
    x = np.array([1.0, 2.5, 7.0])
    assert np.allclose(convert(convert(x, "um", "mm"), "mm", "um"), x)
    assert math.isclose(convert(180.0, "deg", "rad"), math.pi)


def test_dimension_mismatch_unknown_unit_and_non_finite_are_refused():
    with pytest.raises(UnitError, match="차원"):
        convert(1.0, "mm", "Pa")
    with pytest.raises(UnitError, match="모르는 단위"):
        convert(1.0, "psi", "Pa")
    with pytest.raises(UnitError, match="NaN"):
        convert(float("nan"), "m", "mm")


def test_header_split_and_column_normalization():
    assert split_header("온도 [degC]") == ("온도", "degC") and split_header("압력(MPa)") == ("압력", "MPa") and split_header("시간") == ("시간", None)
    names, cols, log = normalize_columns(["시간 [ms]", "온도 [degC]", "메모"], [np.array([0.0, 500.0]), np.array([20.0, 30.0]), np.array([1.0, 2.0])],
                                         {"시간": "s", "온도": "K"})
    assert names[0] == "시간 [s]" and np.allclose(cols[0], [0.0, 0.5]) and np.allclose(cols[1], [293.15, 303.15])
    assert names[2] == "메모" and log[2]["converted"] is False


def test_missing_unit_is_not_guessed():
    with pytest.raises(UnitError, match="추측하지 않습니다"):
        normalize_columns(["온도"], [np.array([20.0, 30.0])], {"온도": "K"})


def test_irregular_times_are_regularized_by_interpolation():
    t = np.array([0.0, 0.9, 2.1, 3.0, 4.2]); y = 2 * t + 1
    a = regularize(t, y, dt=1.0, max_gap=2.0)
    assert np.allclose(a.values, 2 * a.t + 1) and a.report["emptied"] == 0


def test_long_gap_is_left_empty_not_invented():
    t = np.array([0.0, 1.0, 2.0, 10.0, 11.0]); y = t.copy()
    a = regularize(t, y, dt=1.0, max_gap=3.0)
    assert np.isnan(a.values[3:10]).all() and int(a.filled.sum()) == 7 == a.report["emptied"]
    assert not np.isnan(a.values[[0, 1, 2, 10, 11]]).any()
    assert a.report["longest_gap_s"] == 8.0


def test_reverse_and_duplicates_are_refused_by_default_and_handled_on_request():
    t = np.array([0.0, 2.0, 1.0, 3.0]); y = np.array([0.0, 2.0, 1.0, 3.0])
    with pytest.raises(AlignError, match="거꾸로"):
        regularize(t, y, 1.0, 5.0)
    a = regularize(t, y, 1.0, 5.0, on_reverse="sort")
    assert np.allclose(a.values, a.t)
    with pytest.raises(AlignError, match="반복"):
        regularize([0.0, 1.0, 1.0, 2.0], [0.0, 1.0, 3.0, 2.0], 1.0, 5.0)
    d = regularize([0.0, 1.0, 1.0, 2.0], [0.0, 1.0, 3.0, 2.0], 1.0, 5.0, on_duplicate="mean")
    assert np.allclose(d.values, [0.0, 2.0, 2.0])


def test_bad_inputs_and_before_after_report_do_not_judge():
    with pytest.raises(AlignError):
        regularize([0.0, 1.0], [1.0, float("nan")], 1.0, 2.0)
    with pytest.raises(AlignError):
        check_time([0.0], )
    t = np.array([0.0, 1.0, 2.0, 3.0]); y = np.array([1.0, 2.0, 3.0, 4.0])
    a = regularize(t, y, 0.5, 2.0)
    r = compare_before_after(t, y, a)
    assert r["judged"] is False and r["emptied_fraction"] == 0.0 and math.isclose(r["mean_after"], 2.5)
