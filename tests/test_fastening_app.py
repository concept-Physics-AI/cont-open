"""대화 중심 체결 화면: 풀어 쓴 답, 추천 문구, 화면을 여는 말, 서버 없이 도는 공개 시연."""
import json
import re
import threading
import urllib.request

from cont.dialogue.fastening_chat import Session
from cont.dialogue.fastening_talk import ASK_FIELD, ASK_PROCESS, ASK_SENSING, ASK_TRUST, START, josa, screen_intent, settings, suggest, talk
from cont.dialogue.serve_fastening import app_page, example, main, make_server, message, tree
from cont.view.fastening_app import IDEAS, render_app


def test_particles_follow_the_last_sound():
    assert [josa(w, "로") for w in ("M12", "8.8", "3", "판", "나사")] == ["로", "로", "으로", "으로", "로"]
    s = Session(*example())
    assert talk(s.say("축방향 하중 12 kN"))["text"].startswith("축방향 하중을 12000 N으로 올렸습니다.")
    assert josa("조임 토크", "을를") == "를" and josa("강도 등급", "을를") == "을" and josa("항복 안전율", "은는") == "은"


def test_reply_is_written_as_sentences_and_every_number_comes_from_the_answer():
    s = Session(*example())
    t = s.say("토크를 75 N·m로 올려 줘")
    k = talk(t)
    assert k["text"].startswith("조임 토크를 75 N·m로 올렸습니다.") and k["alert"] == "볼트 응력이 항복강도를 넘었습니다." and k["alert_low"]
    assert t.after.value("bolt_equivalent_stress_working") > s.joint.yield_strength              # 그 문장은 계산값에서 나왔다
    k = talk(s.say("토크 40으로"))
    assert k["text"].startswith("조임 토크를 40 N·m로 내렸습니다.")
    k = talk(s.say("M12로 바꿔"))
    assert "규격을 M12로 바꿨습니다." in k["text"] and "표준값으로 맞췄습니다" in k["text"]
    shown = re.search(r"(\S+ 안전율)은 ([\d.]+)이?가? 되었습니다", k["text"])
    if shown:                                                                                       # 문장 속 숫자는 답변 묶음의 값이다
        keys = {"항복 안전율": "safety_yield", "미끄럼 안전율": "safety_slip", "벌어짐 안전율": "safety_opening", "피로 안전율": "safety_fatigue"}
        assert f"{s.answer.value(keys[shown.group(1)]):.2f}" == shown.group(2)
    assert "찾지 못했습니다" in talk(s.say("오늘 점심 뭐 먹지"))["text"]
    bad = talk(s.say("M7로 바꿔"))
    assert "그대로" in bad["text"] and "M7" in bad["alert"]


def test_suggestions_follow_the_state_and_never_repeat_what_was_just_said():
    s = Session(*example())
    first = suggest(s)
    step = settings()["suggest_torque_step"]
    assert first[0] == f"토크를 {50 + step:g} N·m로 올려 줘" and {ASK_FIELD, ASK_TRUST, ASK_SENSING} <= set(first) and len(first) <= settings()["suggest_count"]
    s.say(first[0])
    after = suggest(s, first[0])
    target = f"{settings()['suggest_safety_target']:g}"
    assert after[0] == f"항복 안전율 {target} 이상이 되게 해 줘" and first[0] not in after
    s.say(after[0])
    assert suggest(s, after[0])[:2] == ["1번으로", "2번으로"]                                       # 추천이 나와 있으면 고르는 말을 먼저 권한다
    assert ASK_TRUST not in suggest(s, ASK_TRUST)


def test_screen_words_open_a_view_without_changing_the_design():
    s = Session(*example())
    before = (s.joint, s.load, len(s.turns))
    f, t, n, st = (screen_intent(x, s) for x in (ASK_FIELD, ASK_TRUST, ASK_SENSING, START))
    assert (f["view"], t["open"], n["open"], st["view"]) == ("field", "trust", "sensing", "shape") and (s.joint, s.load, len(s.turns)) == before
    assert "실측과 대조하기 전" in f["talk"]["text"] and "실측과 대조하지 않은" in t["talk"]["text"] and "µm" in n["talk"]["text"]
    assert f"{s.answer.value('preload'):,.0f} N" in st["talk"]["text"] and st["talk"]["text"].startswith("예제 조인트로 시작합니다.")
    assert screen_intent("토크 80으로", s) is None and screen_intent("M12로 바꿔", s) is None
    m = message(s, ASK_FIELD)
    assert m["state"] is None and m["ui"] == {"view": "field", "open": None} and m["brief"] is None        # 그림은 그대로 두고 화면만 연다
    m = message(s, "토크 80으로")
    assert m["state"]["marks"]["glow"] and m["brief"]["kind"] == "changed" and m["ui"] is None and m["suggest"]


def test_page_has_two_scroll_areas_and_a_fixed_composer():
    s = Session(*example())
    page = app_page(s)
    assert page.startswith("<!DOCTYPE html>") and page.count("<canvas") == 1 and 'data-mode="empty"' in page
    assert "무엇을 설계할까요?" in page and all(f'data-say="{t}"' in page for t, _ in IDEAS)
    assert all(x in page for x in ('id="thread"', 'id="latest"', "최신 답으로", 'id="sugg"', 'id="say"', 'id="drawer"',
                                   'data-d="values"', 'data-d="trust"', 'data-d="sensing"', "값 전체", "믿어도 되는가", "현장에서 재려면"))
    assert all(x in page for x in ('data-v="shape"', 'data-v="section"', 'data-v="graph"', 'data-v="field"', "3D CAD", "물리 이미지"))
    assert "계산값 · 검증 전" in page and "실측과 대조하기 전" in page and "합격입니다" not in page
    css = page[page.index("<style>"):page.index("</style>")]
    assert "body{margin:0;overflow:hidden" in css and ".thread{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain" in css
    assert ".drawer{flex:1 1 0;min-height:0;overflow-y:auto;overscroll-behavior:contain" in css and "prefers-reduced-motion" in css
    assert ".rcard.open .stage.stage{flex:0 0 56px" in css and "그림 펼치기" in page          # 묶음을 열면 그림 상자가 위로 접힌다
    assert "@media (max-width:900px)" in css and "env(safe-area-inset-bottom)" in css and ":focus-visible" in css
    data = json.loads(re.search(r'<script type="application/json" id="app-data">(.*?)</script>', page, re.S).group(1))
    assert data["ask_url"] == "/ask" and data["reset_url"] == "/reset" and data["nodes"]["start"]["suggest"] == suggest(s)
    assert 'href="/joint.step"' in page and "github.com/concept-Physics-AI/cont-open" in page


def test_public_demo_is_a_precomputed_tree_that_follows_the_suggested_words(tmp_path):
    data = tree(max_states=4)
    nodes, states = data["nodes"], data["states"]
    assert list(nodes["start"]["next"]) == [t for t, _ in IDEAS] and len(states) <= 4 + 1
    for n in nodes.values():
        assert n["sid"] in states and all(v in nodes for v in n["next"].values())
    started = nodes[nodes["start"]["next"][START]]
    assert started["sid"] == nodes["start"]["sid"] and started["talk"]["text"].startswith("예제 조인트로 시작합니다.")
    raised = nodes[next(v for k, v in started["next"].items() if k.startswith("토크를"))]
    assert raised["sid"] != started["sid"] and raised["brief"]["chips"] and raised["talk"]["alert_low"]
    field = nodes[raised["next"][ASK_FIELD]]
    assert field["sid"] == raised["sid"] and field["ui"]["view"] == "field"                             # 화면만 바꾸는 말은 상태를 새로 싣지 않는다
    json.dumps(data)
    page = render_app(data)
    blob = json.loads(re.search(r'id="app-data">(.*?)</script>', page, re.S).group(1))
    assert blob["ask_url"] is None and "공개 시연" in page and "joint.step" not in page
    out = tmp_path / "app.html"
    main(["--out", str(out)])
    assert 'id="app-data"' in out.read_text(encoding="utf-8")


def test_server_answers_the_chat_screen_and_starts_over_on_reset():
    s = Session(*example())
    srv = make_server(s, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(path, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else b"", headers={"Content-Type": "application/json"}, method="POST")
        return json.loads(urllib.request.urlopen(req, timeout=5).read())
    try:
        assert 'id="app-data"' in urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        d = post("/ask", {"text": "M12로 바꿔"})
        assert d["state"]["size"] == "M12" and "규격을 M12로 바꿨습니다." in d["talk"]["text"] and d["suggest"] and "말을 읽은 방법" in d["detail"]
        assert post("/ask", {"text": ASK_SENSING})["ui"]["open"] == "sensing"
        assert '"size":"M12"' in urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        assert post("/reset") == {}
        assert '"size":"M10"' in urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        assert 'id="live-data"' in urllib.request.urlopen(base + "/live", timeout=5).read().decode("utf-8")     # 예전 화면도 남아 있다
    finally:
        srv.shutdown(); srv.server_close()


def test_picture_can_be_saved_as_an_image_and_the_field_uses_one_hue():
    from cont.view.field_image import BELOW, RAMP
    page = app_page(Session(*example()))
    assert 'id="shot"' in page and "이미지 저장" in page and "function exportImage()" in page and "toBlob" in page
    assert "실측과 대조하기 전입니다" in page[page.index("function exportImage()"):]                 # 내보낸 그림에도 값의 지위를 적는다
    light = [sum(c) for _, c in RAMP]
    assert light == sorted(light) and all(c[0] >= c[2] for _, c in RAMP[1:])                       # 값이 클수록 밝고, 푸른 쪽으로 가지 않는다
    assert BELOW[2] > BELOW[0]                                                                      # 0보다 작은 곳은 다른 색(청회색)


def test_tightening_process_recomputes_each_torque_step_and_can_be_played_and_recorded():
    from dataclasses import replace

    from cont.packs.fastening.pack import answer
    from cont.packs.fastening.process import settings as process_settings, tightening
    j, l = example()
    frames = tightening(j, l)
    assert len(frames) == process_settings()["steps"] + 1 and frames[0] == {"torque": 0.0, "preload": 0.0, "stress": 0.0, "use": 0.0, "elongation": 0.0}
    last, full = frames[-1], answer(j, l)
    assert last["torque"] == l.tightening_torque and last["preload"] == full.value("preload")            # 마지막 칸은 지금 설계의 값과 같다
    assert last["stress"] == full.value("bolt_equivalent_stress_assembly") and abs(last["use"] - last["stress"] / j.yield_strength) < 1e-12
    half = answer(j, replace(l, tightening_torque=frames[12]["torque"]))
    assert frames[12]["preload"] == half.value("preload")                                                # 가운데 칸도 그 토크로 다시 계산한 값이다
    assert [f["preload"] for f in frames] == sorted(f["preload"] for f in frames) and len(tightening(j, l, steps=4)) == 5
    s = Session(*example())
    m = message(s, ASK_PROCESS)
    assert m["ui"] == {"view": "time", "open": None} and m["state"] is None and "풀림은 담지 않습니다" in m["talk"]["text"] and not s.turns
    assert ASK_PROCESS in suggest(s)
    page = app_page(s)
    assert all(x in page for x in ('data-v="time"', 'id="tlplay"', 'id="tlr"', 'id="tlrec"', "영상 저장", "MediaRecorder", "조이는 동안의 마찰 변화나 풀림은 담지 않습니다"))
    data = json.loads(re.search(r'id="app-data">(.*?)</script>', page, re.S).group(1))
    assert len(data["states"]["s0"]["timeline"]) == len(frames) and data["states"]["s0"]["play_seconds"] == process_settings()["play_seconds"]


def test_truth_line_is_drawn_at_the_bottom_of_the_studio_screen_from_the_answer():
    from cont.view.fastening_live import state
    s = Session(*example())
    page = app_page(s)
    assert 'id="truth"' in page and "s.truth_line" in page
    st = json.loads(json.dumps(__import__("cont.dialogue.serve_fastening", fromlist=["live_state"]).live_state(s)))
    line = st["truth_line"]
    assert line == s.answer.truth_line() if hasattr(s, "answer") else line.startswith("해석")
    assert "증거 수준 E1" in line and "검증 전" in line and "렌더러 버전·사람 승인: 보고하지 않음" in line   # 화면이 따로 계산하지 않고 묶음이 낸 줄을 그대로 보인다
