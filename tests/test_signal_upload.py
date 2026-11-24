"""내 신호(CSV) 올리기: 읽기, 검사, 분석, 서버 길."""
import json
import threading
import urllib.request

import numpy as np
import pytest

from cont.fab.own_signal import analyze
from cont.signal.csvio import parse_table, sampling


def _csv(fs=1000.0, n=4000, hz=50.0, amp=3.0, header=True, delim=",", jitter=0.0):
    t = np.arange(n) / fs
    if jitter:
        t = t + np.random.default_rng(0).uniform(-jitter, jitter, n) / fs
    x = amp * np.sin(2 * np.pi * hz * t)
    rows = [f"{a:.6f}{delim}{b:.6f}" for a, b in zip(t, x)]
    return ("time" + delim + "acc\n" if header else "") + "\n".join(rows)


def test_parse_header_delimiters_and_bom():
    for d in (",", "\t", ";"):
        t = parse_table("﻿" + _csv(n=50, delim=d))
        assert t.names == ["time", "acc"] and t.rows == 50
    assert parse_table(_csv(n=20, header=False)).names == ["열 1", "열 2"]


@pytest.mark.parametrize("text,msg", [("a,b\n1,2\n3,x\n", "숫자로 읽지"), ("a,b\n1,2\n3\n", "칸 수"), ("a,b\n1,\n3,4\n", "숫자로 읽지"), ("a\n", "줄이 너무 적"), ("a,b\n1,2\n3,1e999\n", "숫자로 읽지")])
def test_bad_files_say_where_and_why(text, msg):
    with pytest.raises(ValueError, match=msg):
        parse_table(text)


def test_sampling_from_time_column_and_non_increasing_time():
    fs, jit = sampling(np.arange(100) / 250.0)
    assert fs == pytest.approx(250.0) and jit < 1e-9
    with pytest.raises(ValueError):
        sampling(np.array([0.0, 1.0, 1.0, 2.0]))


def test_spectrum_of_uploaded_sine_reads_frequency_and_amplitude():
    s = analyze("spectrum", {"csv": _csv(), "column": 1, "time_column": 0, "filename": "a.csv", "unit": "g"})
    f = dict(map(tuple, s["facts"]))
    assert f["봉우리"] == "50 Hz" and f["50 Hz 성분"] == "3 g" and f["샘플링 주파수"] == "1000 Hz" and "내 자료" in f["신호"]
    assert s["own"] is True and s["label"] == "내 신호 · a.csv" and "<svg" in s["html"]


def test_spectrum_with_typed_sampling_frequency_and_fmax():
    s = analyze("spectrum", {"csv": _csv(header=False), "column": 1, "time_column": -1, "fs": 1000, "fmax": 200})
    assert dict(map(tuple, s["facts"]))["보인 범위"].endswith("200 Hz")


def test_spectrogram_and_distribution_and_refusals():
    s = analyze("spectrogram", {"csv": _csv(n=6000), "column": 1, "time_column": 0})
    assert "가장 큰 성분" in dict(map(tuple, s["facts"]))
    d = analyze("values", {"csv": "v\n" + "\n".join(str(x) for x in np.random.default_rng(1).normal(5, 0.1, 100)), "column": 0, "unit": "mm"})
    assert dict(map(tuple, d["facts"]))["개수"] == "100개"
    with pytest.raises(ValueError, match="일정하지"):
        analyze("spectrum", {"csv": _csv(jitter=0.3), "column": 1, "time_column": 0})
    with pytest.raises(ValueError, match="샘플링 주파수"):
        analyze("spectrum", {"csv": _csv(), "column": 1, "time_column": -1})
    with pytest.raises(ValueError, match="64개"):
        analyze("spectrum", {"csv": _csv(n=30), "column": 1, "time_column": 0})
    with pytest.raises(ValueError, match="같습니다"):
        analyze("spectrum", {"csv": _csv(), "column": 1, "time_column": 1})
    with pytest.raises(ValueError, match="10개"):
        analyze("values", {"csv": "v\n1\n2\n3\n", "column": 0})


def test_server_route_returns_a_sample_or_a_reason():
    from cont.fab.store import make_server
    srv = make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def post(body):
        r = urllib.request.Request(f"http://127.0.0.1:{port}/analyze", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(r).read())
    ok = post({"key": "signal_spectrum", "csv": _csv(), "column": 1, "time_column": 0, "filename": "x.csv"})
    assert ok["own"] and ok["label"] == "내 신호 · x.csv"
    assert "이 파일로는 볼 수 없습니다" in post({"key": "signal_spectrum", "csv": "a,b\n1,x\n2,3\n", "column": 1, "time_column": 0})["error"]
    assert "받지 않습니다" in post({"key": "fastening_section", "csv": "a\n1\n2\n", "column": 0})["error"]
    srv.shutdown()


def test_page_has_upload_form_only_when_server_route_is_given():
    from cont.fab.catalog import catalog
    from cont.fab.store import render_store
    live = render_store(catalog(), make_url="/make", analyze_url="/analyze")
    static = render_store(catalog())
    assert '"analyze_url":"/analyze"' in live and '"analyze_url":null' in static
    assert 'id="own-file"' in static and "서버로 띄운 화면" in static      # 정적 화면은 입력란 대신 안내를 보인다
