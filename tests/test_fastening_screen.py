import json
import threading
import urllib.request

import pytest

from cont.dialogue.fastening_chat import Session, apply, parse
from cont.dialogue.serve_fastening import example, main, make_server, page
from cont.llm import LLMResponse
from cont.packs.fastening import answer, vdi2230
from cont.packs.fastening.curves import joint_diagram, torque_preload
from cont.view import render_fastening


class Fake:
    name, model = "fake", "fake"

    def __init__(self, text=None, error=None):
        self.text, self.error, self.seen = text, error, None

    def complete(self, messages, **opts):
        self.seen = messages
        if self.error:
            raise self.error
        return LLMResponse(self.text, self.name, self.model)


def test_curves_agree_with_the_calculation():
    j, l = example()
    r = vdi2230.calculate(j, l)
    tp = torque_preload(j, l)
    assert tp.preload == pytest.approx(r.preload) and tp.slope_min * l.tightening_torque == pytest.approx(r.preload_min)
    assert tp.slope_max * l.tightening_torque == pytest.approx(r.preload_max) and tp.slope_min < tp.slope < tp.slope_max
    at_yield = vdi2230.calculate(j, l.__class__(**{**l.__dict__, "tightening_torque": tp.preload_at_yield / tp.slope, "friction_range": None}))
    assert at_yield.stress_assembly == pytest.approx(j.yield_strength, rel=1e-6)        # 그 체결력에서 조임 등가응력이 항복강도
    jd = joint_diagram(j, l)
    assert jd.bolt_extra + jd.plate_relief == pytest.approx(l.axial_load_max)             # 운전 하중은 볼트와 판이 나눠 받는다
    assert jd.bolt_elongation / jd.plate_compression == pytest.approx(r.delta_s / r.delta_p)


def test_words_are_read_into_changes():
    assert parse("M12로 바꾸고 토크 80으로") == {"size": "M12", "tightening_torque": 80.0}
    assert parse("머리 쪽 판 두께 20, 축방향 하중 8 kN") == {"plate_head_thickness": 20.0, "axial_load_max": 8000.0}
    assert parse("너트쪽 판을 12mm로, 바깥지름 50") == {"plate_nut_thickness": 12.0, "outer_diameter": 50.0}
    assert parse("판 두께 18") == {"plate_thickness": 18.0}
    assert parse("강도 등급 8.8") == {"property_class": "8.8"} and parse("12.9급으로") == {"property_class": "12.9"}
    assert parse("마찰 0.10~0.16") == {"friction_range": [0.1, 0.16]} and parse("마찰계수를 0.14로") == {"friction": 0.14}
    assert parse("축직각 하중 2000 N, 판 사이 마찰 0.2") == {"transverse_load": 2000.0, "friction_interface": 0.2}
    assert parse("안녕하세요") == {}


def test_a_change_recalculates_and_the_next_turn_starts_from_it():
    s = Session(*example())
    t1 = s.say("토크 60으로 올려줘")
    assert t1.changes == {"tightening_torque": 60.0} and t1.after.value("preload") == pytest.approx(t1.before.value("preload") * 1.2)
    assert "조임 토크: 50 → 60 N·m" in t1.reply and "조립 체결력: 30,542 → 36,650 N" in t1.reply
    t2 = s.say("M12로 바꾸고 머리 쪽 판 두께 20")
    assert (s.joint.size, s.joint.p, s.joint.hole, s.joint.clamp_length) == ("M12", 1.75, 13.5, 35.0) and s.load.tightening_torque == 60.0
    assert t2.before is t1.after and "표준값으로 돌아갑니다" in t2.reply
    assert s.answer.value("safety_yield") == pytest.approx(answer(s.joint, s.load).value("safety_yield"))


def test_bad_or_empty_requests_leave_the_joint_alone():
    s = Session(*example()); start = s.answer
    for text, word in (("M7로 바꿔", "M7"), ("강도 등급 7.7", "7.7"), ("바깥지름 5", "outer_diameter")):
        t = s.say(text)
        assert t.changes == {} and t.reply.startswith("바꾸지 못했습니다") and word in t.reply and s.answer is start
    assert s.say("오늘 날씨 어때").reply.startswith("바꿀 값을 찾지 못했습니다") and s.joint.size == "M10"
    j, l = example()
    with pytest.raises(ValueError):
        apply(j, l, {"tightening_torque": -5.0})


def test_llm_only_names_what_to_change_and_is_checked():
    s = Session(*example(), provider=Fake('바꿀 항목입니다: {"size": "M16", "tightening_torque": 120}'))
    t = s.say("볼트를 한 단계 굵게 하고 그에 맞게 토크도 올려줘")
    assert t.source == "llm" and t.changes == {"size": "M16", "tightening_torque": 120.0} and s.joint.size == "M16"
    assert "계산 결과를 만들지 않는다" in s.provider.seen[0].content
    for bad in ('{"safety_yield": 3.0}', '{"tightening_torque": "많이"}', "잘 모르겠습니다", '{"friction_range": 0.1}'):
        s2 = Session(*example(), provider=Fake(bad))
        t2 = s2.say("토크 70으로")
        assert t2.source == "rule" and t2.changes == {"tightening_torque": 70.0} and "규칙으로 읽음" in t2.note
    s3 = Session(*example(), provider=Fake(error=ConnectionError("down")))
    assert s3.say("토크 70으로").changes == {"tightening_torque": 70.0}
    s4 = Session(*example(), provider=Fake("{}"))
    assert s4.say("그냥 물어봤어요").changes == {}


def test_screen_draws_the_joint_and_never_says_pass_or_fail(tmp_path):
    j, l = example()
    a = answer(j, l)
    html_text = render_fastening(j, l, a)
    assert html_text.startswith("<!DOCTYPE html>") and html_text.count("<svg") == 3 and "http" not in html_text
    assert all(t in html_text for t in ("체결 선도", "토크-체결력", "안전율", "l_K 30", "M10")) and "대화로 바꾸기" not in html_text
    assert "합격·불합격은 표시하지 않습니다" in html_text and "불합격입니다" not in html_text and "합격입니다" not in html_text
    out = tmp_path / "f.html"
    main(["--out", str(out), "--classic"])
    demo = out.read_text(encoding="utf-8")
    assert "대화로 바꾸기" in demo and "M12 · 12.9" in demo and "바꾸기 전" in demo and "<form" not in demo and "(이전 " in demo
    assert "목표를 만족하는 조합은" in demo and "1번: 강도 등급 12.9" in demo


def test_server_applies_what_is_said_and_shows_the_new_state():
    s = Session(*example())
    srv = make_server(s, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert "<form" in urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        req = urllib.request.Request(base + "/say", data=json.dumps({"text": "M12로 바꿔"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        d = json.loads(urllib.request.urlopen(req, timeout=5).read())
        assert d["changes"] == {"size": "M12"} and "규격: M10 → M12" in d["reply"]
        assert "M12 · 10.9" in urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        bad = urllib.request.Request(base + "/say", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(bad, timeout=5)
    finally:
        srv.shutdown(); srv.server_close()
    assert "대화로 바꾸기" in page(s, None)
