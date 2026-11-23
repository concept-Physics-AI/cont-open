"""설비 이상진단 화면 (ConT Fab으로 만든 화면의 한 예): 진단 결과를 관찰 사실 · 원인 후보 · 다음 점검으로, 값은 진단 팩이 낸 것만."""
import json
import re
import threading
import urllib.request

from cont.dialogue.serve_diagnosis import QUESTIONS, demo_cases, main, make_server, synthetic_cutting
from cont.packs.diagnosis.demo import synthetic_equipment
from cont.packs.diagnosis.guidance import guide
from cont.packs.diagnosis.report import report
from cont.view.diagnosis_app import STATES, render_diagnosis_app


def test_report_splits_each_finding_into_fact_candidates_and_checks():
    eq, it = synthetic_cutting()
    cards = report(eq, it)
    assert [c.title for c in cards] == [f.label for f in it.findings] and all(c.kind == "special" for c in cards)
    for c, f in zip(cards, it.findings):
        assert (c.start, c.end, c.peak_z) == (f.start, f.end, f.peak_z)                     # 특화 해석의 구간과 값 그대로
        assert f"{f.start:g}부터 {f.end:g}까지" in c.observed.text and f"{abs(f.peak_z):.1f}배" in c.observed.text
        assert c.candidates[0].text.startswith(f.label) and f.meaning in c.candidates[0].text and c.checks
    assert "높았습니다" in cards[0].observed.text and "낮았습니다" in cards[1].observed.text
    tags = [c.observed.tag for c in cards] + [t.tag for c in cards for t in c.candidates + c.checks]
    assert len(tags) == len(set(tags)) and tags[0] == "E-01" and all(re.fullmatch(r"[EHM]-\d\d", t) for t in tags)


def test_common_findings_take_candidates_and_checks_from_the_knowledge_table():
    eq = synthetic_equipment()
    g = guide(eq)
    cards = report(eq, guidance=g)
    assert len(cards) == len(g.items) and all(c.kind == "common" for c in cards)
    for c, it in zip(cards, g.items):
        assert [t.text for t in c.checks] == [x.check for x in it.candidates]
        assert [t.text for t in c.candidates] == [x.cause for x in it.candidates if x.cause]
        d = next(s.diagnosis for s in eq.systems if s.name == c.system)
        r = next(x for x in d.signals if x.column == c.signal)
        assert any(float(d.time[iv.start]) == c.start and iv.peak_z == c.peak_z for iv in r.intervals)   # 숫자는 진단 팩의 구간에서 온다
    assert not any("가열 구역" == c.system for c in cards)                                # 정상인 계통에는 카드가 없다


def test_page_has_site_settings_signals_and_agent_and_never_judges(tmp_path):
    out = tmp_path / "fab.html"
    main(["--out", str(out)])
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!DOCTYPE html>") and all(x in page for x in ("설비 이상진단", "ConT Fab으로 만든 화면", "현장 설정", "운전조건", "정상 기준", "입력 신호", "ConT Agent",
                                                                           "관찰 사실", "원인 후보", "다음 점검", "확정한 원인이 아닙니다", "가상 데이터 시연"))
    assert "합격·불합격의 기준이 아니며" in page and "아직 저장하지 않습니다" in page and "합격입니다" not in page
    data = json.loads(re.search(r'<script type="application/json" id="app-data">(.*?)</script>', page, re.S).group(1))
    assert data["ask_url"] is None and data["states"] == list(STATES) == ["미확인", "점검 중", "조치", "재확인"]
    cut, eqp = data["cases"]
    assert cut["id"] == "cutting" and cut["synthetic"] and [c["title"] for c in cut["cards"]] == ["공구 마모 진행 의심", "공구 파손 의심"]
    assert [q["q"] for q in cut["questions"]] == list(QUESTIONS) and all(q["a"] and "규칙" in q["src"] for q in cut["questions"])
    assert len(eqp["systems"]) == 4 and [s["found"] for s in eqp["systems"]].count(0) == 1
    sig = cut["systems"][0]["signals"][0]
    assert sig["chart"].startswith("<svg") and sig["label"] == "전류" and float(sig["peak"]) > 0 and cut["systems"][0]["signals"][1]["peak"] is None
    assert cut["confidence"] == "낮음"


def test_server_answers_a_typed_question_from_the_diagnosis():
    srv = make_server(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        home = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        assert '"ask_url":"/ask"' in home
        req = urllib.request.Request(base + "/ask", data=json.dumps({"question": "무엇부터 점검해야 하나요?", "case": "cutting"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        d = json.loads(urllib.request.urlopen(req, timeout=5).read())
        assert "원인은 판정하지 않았습니다" in d["answer"] and "규칙" in d["source"]
        bad = urllib.request.Request(base + "/ask", data=json.dumps({"question": "?", "case": "none"}).encode(), method="POST")
        try:
            urllib.request.urlopen(bad, timeout=5); raise AssertionError("should fail")
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        srv.shutdown(); srv.server_close()
    cases, kept = demo_cases()
    assert set(kept) == {"cutting", "equipment"} and render_diagnosis_app(cases).count("<option") == 2
