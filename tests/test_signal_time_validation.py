"""시간 메타데이터 오류가 그럴듯한 주파수 그래프로 바뀌지 않아야 한다."""
import numpy as np
import pytest

from cont.fab.own_signal import analyze
from cont.signal import spectrum, spectrogram
from cont.signal.csvio import sampling


@pytest.mark.parametrize("time", [
    [0, np.nan, 2], [0, np.inf], [-np.inf, 0], [0, 1, 1], [2, 1],
    [], [0], [[0, 1], [2, 3]], 1.0, [-1e308, 1e308], [0, 5e-324],
])
def test_invalid_time_axis_is_refused(time):
    with pytest.raises(ValueError):
        sampling(np.asarray(time))


def test_relative_time_can_start_before_zero_and_jitter_is_reported():
    fs, jitter = sampling(np.array([-1.0, -0.5, 0.0, 0.6]))
    assert fs == pytest.approx(2.0)
    assert jitter == pytest.approx(0.2)


def test_large_finite_intervals_do_not_overflow_median():
    fs, jitter = sampling(np.array([-1e308, 0.0, 1e308]))
    assert fs == pytest.approx(1e-308, rel=1e-12, abs=0)
    assert jitter == 0


@pytest.mark.parametrize("unit,scale", [("s", 1), ("ms", 1000), ("us", 1e6)])
def test_explicit_time_units_produce_the_same_frequency(unit, scale):
    time = np.arange(1000) / 1000
    assert sampling(time * scale, unit)[0] == pytest.approx(1000)
    csv = "time,value\n" + "\n".join(f"{t * scale:.9f},{v:.9f}" for t, v in
                                   zip(time, np.sin(2 * np.pi * 50 * time)))
    card = analyze("spectrum", {"csv": csv, "column": 1, "time_column": 0, "time_unit": unit})
    facts = dict(card["facts"])
    assert facts["봉우리"] == "50 Hz"
    assert facts["샘플링 주파수"] == "1000 Hz"
    assert facts["시간 열"] == f"time ({unit} → s)"


def test_unknown_time_unit_is_not_guessed():
    with pytest.raises(ValueError, match="시간 단위"):
        sampling(np.array([0, 1, 2]), "ticks")


@pytest.mark.parametrize("fs", [np.nan, np.inf, -np.inf, 0.0, -1.0])
def test_nonfinite_frequency_is_refused_before_fft(fs):
    for engine in (spectrum, spectrogram):
        with pytest.raises(ValueError, match="샘플링 주파수"):
            engine(np.arange(64), fs)


@pytest.mark.parametrize("window", [0, 1, 2, -3, True, 3.5, np.nan, np.inf])
def test_invalid_window_cannot_make_zero_weight_spectrum(window):
    with pytest.raises(ValueError, match="창 길이"):
        spectrogram(np.arange(64), 100.0, window=window)


@pytest.mark.parametrize("field", ["fs", "fmax"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_fab_rejects_nonfinite_manual_frequency(field, value):
    payload = {"csv": "v\n" + "\n".join(str(i) for i in range(64)),
               "column": 0, "time_column": -1, "fs": 100, field: value}
    with pytest.raises(ValueError, match="유한"):
        analyze("spectrum", payload)
