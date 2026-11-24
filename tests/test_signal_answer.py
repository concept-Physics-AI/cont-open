"""신호 분석 결과가 공통 결과 형식(PhysicsAnswer)으로 나오고, FAB 카드가 그 묶음의 믿을 근거를 보이는지 확인한다."""
import numpy as np
import pytest

from cont.answer import NOT_REPORTED, STATUS_OBSERVED, STATUS_SIMULATED, PhysicsAnswer
from cont.signal import distribution, peaks, spectrogram, spectrum
from cont.signal.answers import distribution_answer, spectrogram_answer, spectrum_answer
from cont.signal.synthetic import repeat_values, run_up, vibration


def _rows(a):
    return {k: v for k, v in a.trust()}


def test_spectrum_answer_carries_peak_status_and_trust_rows():
    fs = 1000.0
    t = np.arange(4000) / fs
    sp = spectrum(3.0 * np.sin(2 * np.pi * 50.0 * t), fs)
    a = spectrum_answer(sp, peaks(sp, 1), "mm/s", "올린 파일", True, {"fs": fs})
    assert isinstance(a, PhysicsAnswer)
    assert a.value("peak1_freq") == pytest.approx(50.0, abs=0.05) and a.value("peak1_amp") == pytest.approx(3.0, rel=0.02)
    assert a.status == STATUS_OBSERVED and a.validation == "unvalidated"
    r = _rows(a)
    assert r["물리잔차"] == NOT_REPORTED                 # 계산하지 않은 항목은 지우지 않고 그렇게 적는다
    assert r["불확실성"] != NOT_REPORTED and "0.25" in r["불확실성"] and r["적용 범위"] != NOT_REPORTED and r["실패 조건"] != NOT_REPORTED


def test_synthetic_signal_is_simulated_not_observed():
    sp = spectrum(vibration(), 2000.0)
    a = spectrum_answer(sp, peaks(sp, 3), "mm/s", "가상 신호", False, {})
    assert a.status == STATUS_SIMULATED


def test_spectrogram_and_distribution_answers():
    sg = spectrogram(run_up(), 2000.0, window=256)
    track = sg.freq[sg.amp.argmax(axis=0)]
    a = spectrogram_answer(sg, track, 256, "가상 신호", False, {})
    assert a.value("segments") == sg.time.size and _rows(a)["물리잔차"] == NOT_REPORTED
    d = distribution(repeat_values(), 12)
    b = distribution_answer(d, "um", "올린 파일", True, {})
    assert b.value("mean") == pytest.approx(d.mean) and "표준오차" in b.uncertainty and b.status == STATUS_OBSERVED


def test_fab_samples_show_trust_in_detail():
    from cont.fab.catalog import catalog
    seen = 0
    for it in catalog():
        if it["key"] in ("signal_spectrum", "signal_spectrogram", "repeat_distribution"):
            for s in it["samples"]:
                assert "이 결과를 믿어도 되는가" in s["more"] and "검증 전" in s["more"] and "가상" in s["more"]
                seen += 1
    assert seen >= 3


def test_own_csv_sample_is_observed_with_trust_rows():
    from cont.fab.catalog import own_sample
    fs = 1000.0
    t = np.arange(2000) / fs
    csv = "t,x\n" + "\n".join(f"{a:.6f},{np.sin(2*np.pi*50*a):.6f}" for a in t)
    s = own_sample("signal_spectrum", {"csv": csv, "column": 1, "time_column": 0, "unit": "mm/s", "filename": "a.csv"})
    assert "올린 파일" in s["more"] and "관측" in s["more"] and "보고하지 않음" in s["more"]
