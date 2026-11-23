import json
import re
import threading
import urllib.request

import pytest

from cont.dialogue.fastening_chat import Session, brief
from cont.dialogue.serve_fastening import example, live_state, main, make_server, scripted
from cont.view import render_live
from cont.view.fastening_live import LINGER_MS, state


def test_brief_is_one_line_a_few_numbers_and_one_thing_to_notice():
    s = Session(*example())
    b = brief(s.say("토크 75로"))
    assert b["kind"] == "changed" and b["headline"] == "바꿨습니다: 조임 토크 75 N·m" and b["said"] == "토크 75로"
    assert 1 <= len(b["chips"]) <= 4 and [c["spot"] for c in b["chips"]].count(True) == 1
    top = b["chips"][0]
    assert (top["label"], top["from"], top["to"], top["dir"], top["spot"]) == ("항복 안전율", 1.43, 0.96, "down", True)
    assert b["alert"] == "항복 안전율이 1.0 아래로 내려갔습니다." and b["alert_low"] is True       # 1.0을 넘나든 것이 가장 먼저
    up = brief(s.say("M12로 바꾸고 머리 쪽 판 두께 20"))
    assert up["alert"] == "항복 안전율이 1.0 위로 올라왔습니다." and up["alert_low"] is False
    assert up["headline"] == "바꿨습니다: 규격 M12, 머리 쪽 판 두께 20 mm"
    same = brief(s.say("토크 75"))
    assert same["chips"] == [] and "계산 결과는 그대로" in same["headline"]
    assert "합격" not in json.dumps(b, ensure_ascii=False)


def test_brief_for_offers_failures_and_unclear_words():
    s = Session(*example())
    s.say("축방향 하중 12 kN")
    offer = brief(s.say("항복 안전율 1.5 이상, 미끄럼 안전율 2.5 이상이 되게 해 줘"))
    assert offer["kind"] == "offer" and offer["headline"].startswith("목표에 맞는 방법 3가지")
    assert offer["options"][0] == {"n": 1, "what": "M16, 토크 112.5 N·m", "detail": "항복 2.62 · 미끄럼 2.51", "say": "1번으로"}
    met = brief(s.say("벌어짐 안전율 2 이상 되게"))
    assert met["headline"].startswith("지금 설계가 이미 목표에 맞습니다") and met["options"][0]["what"] == "지금 그대로"
    bad = brief(s.say("M7로 바꿔"))
    assert bad["kind"] == "failed" and bad["headline"] == "바꾸지 못했습니다." and bad["alert_low"]
    assert bad["alert"] == "M7은(는) 표준 데이터에 없는 규격입니다. 쓸 수 있는 규격: M6, M8, M10, M12, M16, M20, M24"
    assert "7.7은(는) 표준 데이터에 없는 강도 등급" in brief(s.say("강도 등급 7.7"))["alert"]
    none = brief(s.say("안녕하세요"))
    assert none["kind"] == "none" and len(none["examples"]) == 4 and none["chips"] == []
    impossible = brief(s.say("피로 안전율 100 이상"))
    assert impossible["kind"] == "failed" and impossible["headline"].startswith("목표(피로 안전율 100 이상)를 만족하는 조합을 찾지 못했습니다")


def test_state_carries_what_the_screen_draws_and_meshes_can_morph_between_states():
    states = scripted(("M16으로 바꿔", "머리 쪽 판 두께 25"))
    assert len(states) == 3 and states[0]["brief"] is None and states[1]["brief"]["said"] == "M16으로 바꿔"
    a, b = states[0], states[1]
    assert (a["title"], b["title"]) == ("M10 · 10.9", "M16 · 10.9") and [t["label"] for t in a["tiles"] if t["group"] == "seen"] == ["조임 토크", "축방향 운전 하중", "체결 길이"]
    assert [len(p["tri"]) for p in a["viewer"]["parts"]] == [len(p["tri"]) for p in b["viewer"]["parts"]]   # 삼각형 수가 같아야 그 자리에서 변한다
    assert a["viewer"]["parts"][1]["tri"] != b["viewer"]["parts"][1]["tri"]
    assert all(v.startswith("<svg") for v in a["views"].values()) and a["views"]["section"] != b["views"]["section"]
    assert [s["label"] for s in a["safety"]][:3] == ["항복", "벌어짐", "미끄럼"] and "바꾸기 전" in b["more"]
    assert states[2]["detail"].startswith("바꿨습니다.") and "말을 읽은 방법: 규칙" in states[2]["detail"]
    json.dumps(states)                                                                              # 그대로 화면에 실을 수 있다


def test_live_page_is_one_file_with_tabs_and_plays_prepared_states(tmp_path):
    out = tmp_path / "live.html"
    main(["--out", str(out)])
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!DOCTYPE html>") and "http" not in page and page.count("<canvas") == 1
    assert all(t in page for t in ('data-v="shape"', 'data-v="section"', 'data-v="diagram"', 'data-v="torque"', "자세히: 물리, 수학·조건"))
    data = json.loads(re.search(r'<script type="application/json" id="live-data">(.*?)</script>', page, re.S).group(1))
    assert len(data["states"]) == 6 and data["ask_url"] is None and data["linger_ms"] == LINGER_MS
    assert [s["brief"]["kind"] for s in data["states"][1:]] == ["changed", "changed", "changed", "offer", "changed"]
    assert "합격입니다" not in page and "불합격입니다" not in page and "prefers-reduced-motion" in page
    with pytest.raises(ValueError):
        render_live([])
    j, l = example()
    from cont.packs.fastening import answer
    one = render_live([state(j, l, answer(j, l))], ask_url="/say", downloads=(("STEP", "/joint.step"),))
    assert '"ask_url":"/say"' in one and 'href="/joint.step"' in one and "말로 바꿔 보세요" in one


def test_server_answers_a_turn_with_the_next_state_so_the_page_changes_in_place():
    s = Session(*example())
    srv = make_server(s, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        home = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        assert 'id="live-data"' in home and '"ask_url":"/say"' in home and "location.reload" not in home
        req = urllib.request.Request(base + "/say", data=json.dumps({"text": "M12로 바꿔"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        d = json.loads(urllib.request.urlopen(req, timeout=5).read())
        assert d["title"] == "M12 · 10.9" and d["brief"]["headline"] == "바꿨습니다: 규격 M12" and d["changes"] == {"size": "M12"}
        assert d["viewer"]["parts"] and d["views"]["torque"].startswith("<svg") and d == {**live_state(s, s.turns[-1]), "reply": d["reply"],
                                                                                         "changes": d["changes"], "source": d["source"]}
        assert "대화로 바꾸기" in urllib.request.urlopen(base + "/classic", timeout=5).read().decode("utf-8")      # 예전 화면도 남아 있다
    finally:
        srv.shutdown(); srv.server_close()


def test_marks_say_where_the_change_is_and_charts_keep_the_old_shape_as_a_ghost():
    """2026-11-23 대표 의견: 대화로 바뀌면 어디가 바뀌는지 표시되어야 한다."""
    from cont.view.fastening_live import marks
    states = scripted(("M12로 바꾸고 머리 쪽 판 두께 20", "토크 80, 강도 등급 12.9", "축방향 하중 12 kN", "안녕"))
    first, sized, tightened, loaded, idle = states
    assert first["marks"] == {"glow": [], "tags": [], "notes": []} and 'class="gh"' not in first["views"]["section"]
    assert sized["marks"]["glow"] == ["bolt_head", "bolt_shank", "nut", "plate_head"]
    assert sized["marks"]["tags"] == [{"role": "bolt_head", "text": "볼트 M10 → M12"}, {"role": "plate_head", "text": "머리 쪽 판 15 → 20 mm"}]
    assert tightened["marks"]["tags"] == [{"role": "bolt_shank", "text": "강도 등급 10.9 → 12.9"}, {"role": "nut", "text": "조임 토크 50 → 80 N·m"}]
    assert loaded["marks"] == {"glow": [], "tags": [], "notes": ["축방향 하중 6,000 → 12,000 N"]}       # 부품이 없는 변화는 글로 알린다
    assert idle["marks"] == {"glow": [], "tags": [], "notes": []}                                       # 바뀐 것이 없으면 표시도 없다
    assert sized["views"]["section"].count('class="gh"') == 5 and 'class="gh"' in sized["views"]["diagram"] and 'class="ghpt"' in sized["views"]["torque"]
    assert 'class="gh"' not in idle["views"]["diagram"]
    assert all("anchor" in p and "reach" in p for p in sized["viewer"]["parts"])
    j, l = example()
    assert marks(j, l, j, l) == {"glow": [], "tags": [], "notes": []}
    page = render_live(states)
    assert all(t in page for t in ("점선은 바꾸기 전입니다", "점선은 바꾸기 전 값입니다", 'class="notes"', ".tabs button.new::after", "--glow"))


def test_screen_separates_seen_physics_from_hidden_physics_and_draws_the_hidden_state():
    """2026-11-23 대표 의견: 물리와 숨은 물리에 대한 내용이 있어야 한다."""
    import math

    from cont.packs.fastening import vdi2230
    from cont.packs.fastening.shape import compression_zone
    from cont.shape import revolve, volume
    j, l = example()
    st = scripted(())[0]
    hidden = [t for t in st["tiles"] if t["group"] == "hidden"]
    assert [t["label"] for t in hidden] == ["조립 체결력", "볼트가 받는 운전 하중의 몫", "남는 체결력 (최소)", "볼트 등가응력", "좌면 압력"]
    r = vdi2230.calculate(j, l)
    assert hidden[0]["range"] == f"마찰에 따라 {r.preload_min:,.0f} ~ {r.preload_max:,.0f}"      # 같은 토크에서도 마찰에 따라 달라진다
    assert hidden[1]["value"] == pytest.approx(r.load_factor * 100) and hidden[2]["value"] == pytest.approx(r.residual_clamp_min)
    assert st["hidden"]["use"] == pytest.approx(r.stress_working / j.yield_strength) and st["hidden"]["yield"] == 940.0
    # 판이 눌리는 영역: 좌면에서 시작해 체결 길이의 가운데에서 가장 넓다 (VDI 2230의 변형 원뿔)
    zone = compression_zone(j)
    tan_phi = vdi2230.cone_angle_tan(j.clamp_length, j.bearing_diameter, j.outer_diameter)
    assert zone[0] == (j.hole / 2, 15.0) and zone[1] == (j.bearing_diameter / 2, 15.0)
    assert zone[2] == pytest.approx((j.bearing_diameter / 2 + 15.0 * tan_phi, 0.0)) and zone[-1] == (j.hole / 2, -15.0)
    wide = compression_zone(j.modified(outer_diameter=20.0))                                   # 바깥지름에 닿으면 그 뒤는 원통
    assert max(p[0] for p in wide) == 10.0 and len(wide) == 6
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(zone, zone[1:] + zone[:1]))) / 2
    cr = abs(sum((a[0] + b[0]) * (a[0] * b[1] - b[0] * a[1]) for a, b in zip(zone, zone[1:] + zone[:1]))) / (6 * area)
    assert volume(revolve(zone)) == pytest.approx(2 * math.pi * cr * area, rel=0.006)          # 회전체의 부피 (파푸스의 정리)
    assert volume(revolve(zone, sweep=270)) == pytest.approx(0.75 * volume(revolve(zone)), rel=1e-6)
    with pytest.raises(ValueError):
        revolve([(1, 0), (2, 0)])
    assert st["viewer"]["parts"][-1]["role"] == "zone"
    page = render_live([st])
    assert all(t in page for t in ("보이는 물리", "숨은 물리", "직접 잴 수 없는 안쪽 상태", "숨은 물리 보기", "결과: 안전율",
                                   "그 토크가 만든 체결력은 직접 잴 수 없습니다", "VDI 2230의 계산 모형이며 해석(FEM) 결과가 아닙니다"))


def test_screen_follows_the_canonical_rules_for_hidden_physics():
    """docs/hidden_physics.md: 값의 지위를 구분한다, 핵심 숫자는 셋까지, 나머지는 눌러서 연다, 불확실성·잔차·검증 상태를 숨기지 않는다."""
    from cont.view.fastening_live import core_numbers, trust
    j, l = example()
    from cont.packs.fastening import answer
    a = answer(j, l)
    core = core_numbers(j, a)
    assert len(core) == 3 and [c["label"] for c in core][:2] == ["조립 체결력", "볼트 응력 ÷ 항복강도"]
    assert core[0]["range"].startswith("마찰에 따라 ") and core[0]["status"] == "숨은 물리 · 해석"          # 불확실성 없는 단일값을 내지 않는다
    lowest = min(v for v in (a.value(k) for k in ("safety_yield", "safety_opening", "safety_slip", "safety_pressure_head",
                                                  "safety_pressure_nut", "safety_fatigue")) if v is not None)
    assert core[2]["value"] == lowest and core[2]["label"].startswith("가장 낮은 안전율 (") and core[2]["low"] is False
    hot = core_numbers(j, answer(j, l.__class__(**{**l.__dict__, "tightening_torque": 80.0})))
    assert hot[1]["low"] is True and hot[2]["low"] is True
    no_range = core_numbers(j, answer(j, l.__class__(**{**l.__dict__, "friction_range": None})))
    assert no_range[0]["range"] == "마찰 범위를 주지 않아 한 값만 있음"
    t = dict(trust(j, l, a))
    assert list(t) == ["값의 지위", "근거 데이터", "사용 모델", "가정", "증거와 식별가능성", "불확실성", "물리잔차", "검증 상태", "적용 범위", "실패 조건"]
    assert t["값의 지위"] == "입력, 해석. 관측·추정한 값은 없음" and t["검증 상태"].startswith("검증 전.")
    assert t["증거와 식별가능성"] == "추정한 값 없음"
    assert "= 0 N" in t["물리잔차"] and "마찰계수 0.1 ~ 0.14" in t["불확실성"] and "편심 하중" in t["실패 조건"]
    st = scripted(("항복 안전율 1.5 이상이 되게",))
    page = render_live(st)
    assert page.count('class="c" id="core') == 3 and page.count('<details class="acc"') == 5
    assert '<details class="acc" id="acc-hidden"><summary>' in page and " open" not in page.split('id="acc-hidden"')[1][:40]   # 닫힌 채로 시작한다
    assert all(x in page for x in ("이 결과를 믿어도 되는가", "관측으로 복원한 값이 아니라 계산 모형으로 구한 값입니다", "생성 후보 (검증 전)",
                                   "센서로 관측한 값이 아니라 사람이 넣은 값입니다", "관측 없음"))
