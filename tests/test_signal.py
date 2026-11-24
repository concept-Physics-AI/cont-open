"""신호 분석 엔진: 알려진 신호를 넣어 성분과 분포를 맞게 읽는지 확인한다."""
import numpy as np
import pytest

from cont.signal import distribution, peaks, spectrogram, spectrum
from cont.signal.synthetic import repeat_values, run_up, vibration


def test_sine_peak_has_the_right_frequency_and_amplitude():
    fs = 1000.0
    t = np.arange(4000) / fs
    sp = spectrum(3.0 * np.sin(2 * np.pi * 50.0 * t), fs)
    (f, a), = peaks(sp, 1)
    assert f == pytest.approx(50.0, abs=0.05) and a == pytest.approx(3.0, rel=0.02)


def test_off_bin_frequency_is_refined_between_bins():
    fs = 1000.0
    t = np.arange(2000) / fs
    sp = spectrum(np.sin(2 * np.pi * 123.4 * t), fs)
    assert peaks(sp, 1)[0][0] == pytest.approx(123.4, abs=0.1) and sp.resolution == pytest.approx(0.5)


def test_machine_vibration_shows_rotation_harmonic_and_fault_tone():
    x = vibration(rpm=1500, unbalance=1.0, harmonic2=0.3, fault_hz=87.0, fault_amp=0.2)
    got = {round(f): a for f, a in peaks(spectrum(x, 2000.0), 5, 0.05)}
    assert set(got) == {25, 50, 87} and got[25] == pytest.approx(1.0, rel=0.05) and got[50] == pytest.approx(0.3, rel=0.1)


def test_dc_offset_is_removed_by_default_and_kept_on_request():
    x = np.full(256, 5.0) + np.sin(np.arange(256) * 0.5)
    assert spectrum(x, 100.0).amp[0] < 0.1 and spectrum(x, 100.0, detrend=False).amp[0] == pytest.approx(5.0, rel=0.05)


def test_spectrogram_follows_a_rising_frequency():
    fs = 2000.0
    sg = spectrogram(run_up(fs=fs, rpm0=600, rpm1=2400), fs, window=512)
    track = sg.freq[sg.amp.argmax(axis=0)]
    assert track[0] == pytest.approx(10.0 + 0.5 * 30 * sg.time[0] / 4 * 2 - 0.0, abs=6)
    assert np.all(np.diff(track) >= -2.0) and track[-1] > track[0] + 20
    assert sg.amp.shape == (sg.freq.size, sg.time.size)


def test_distribution_reports_mean_spread_and_outliers():
    d = distribution(repeat_values(n=400, mean=10.0, std=0.05, outliers=3), bins=10)
    assert d.n == 400 and d.counts.sum() == 400 and len(d.outliers) >= 3
    assert d.mean == pytest.approx(10.0, abs=0.05) and d.q1 < d.median < d.q3
    assert distribution(repeat_values(std=0.05, outliers=0)).std == pytest.approx(0.05, rel=0.2)


@pytest.mark.parametrize("bad", [np.array([1.0, 2.0]), np.array([1.0] * 7 + [np.nan])])
def test_bad_signals_are_refused(bad):
    with pytest.raises(ValueError):
        spectrum(bad, 100.0)
    with pytest.raises(ValueError):
        spectrum(np.zeros(64), 0.0)
    with pytest.raises(ValueError):
        distribution(np.array([1.0, 2.0]))


def test_fab_cards_are_made_by_the_engine_and_say_they_are_synthetic():
    from cont.fab.catalog import catalog, types_data
    items = {i["key"]: i for i in catalog()}
    for k, n in (("signal_spectrum", 3), ("signal_spectrogram", 2), ("repeat_distribution", 4)):
        assert len(items[k]["samples"]) == n
        assert all("가상" in dict(map(tuple, s["facts"])).get("신호", dict(map(tuple, s["facts"])).get("값", "")) for s in items[k]["samples"])
    peaks_fact = [dict(map(tuple, s["facts"]))["봉우리"] for s in items["signal_spectrum"]["samples"]]
    assert peaks_fact == ["25 Hz · 50 Hz", "25 Hz · 50 Hz", "25 Hz · 50 Hz · 87 Hz"]       # 성분을 알고 만든 신호를 맞게 읽었다
    covered = {t["key"]: t["covered_by"] for t in types_data()["types"]}
    assert covered["sig_spectrum"] == ["signal_spectrum"] and covered["gr_repeat"] == ["repeat_distribution"]


def test_physics_page_moves_signal_analysis_from_wanted_to_ready():
    from cont.view.physics_page import engines_ready, engines_wanted
    assert "signal_analysis" in {x["key"] for x in engines_ready()} and "signal" not in {x["key"] for x in engines_wanted()}


def test_close_peak_labels_do_not_overlap_and_all_peak_sizes_listed():
    import re
    from cont.fab.signal_views import spectrum_sample
    from cont.signal import spectrum
    from cont.signal.synthetic import vibration
    sp = spectrum(vibration(fs=1000, seconds=2, rpm=3000, unbalance=1.0, harmonic2=0.3, fault_hz=87.0, fault_amp=0.25), 1000)
    r = spectrum_sample(sp, "t", 150, 3, 0.1, "mm/s", "가상")
    ys = [(float(x), float(y)) for x, y in re.findall(r'<text class="tick" x="([\d.]+)" y="(\d+)"[^>]*>\d+ Hz</text>', r["html"])]
    for i, a in enumerate(ys):
        for b in ys[i + 1:]:
            assert abs(a[0] - b[0]) >= 70 or a[1] != b[1]
    n_peaks = len(r["facts"][0][1].split(" · "))
    assert sum(1 for k, _ in r["facts"] if k.endswith(" Hz 성분")) == n_peaks
