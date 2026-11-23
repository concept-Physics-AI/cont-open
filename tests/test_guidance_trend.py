import json
import threading
import urllib.request

import numpy as np
import pytest

from cont import packs
from cont.dialogue import ask
from cont.dialogue.serve import make_server
from cont.packs.diagnosis import diagnose_equipment, guide, site_special, trend
from cont.packs.diagnosis import synthetic as syn
from cont.packs.diagnosis.demo import main as demo_main
from cont.packs.diagnosis.demo import synthetic_equipment
from cont.packs.diagnosis.profile import load_guidance, load_module, load_special, modules, specials
from cont.packs.diagnosis.special import interpret
from cont.view import render_equipment

SPINDLE = {"name": "주축", "module": "drive", "normal": syn.drive(3000, seed=41), "time": "t",
           "signals": {"current": "current", "vibration": "vibration"}, "conditions": {"load": "load", "speed": "speed"}}


@pytest.fixture(scope="module")
def eq():
    return synthetic_equipment()


def test_every_change_type_and_every_special_rule_has_something_to_check():
    table = load_guidance()
    for m in modules():
        for ct in load_module(m).change_types:
            rows = table[m][ct.key]
            assert rows and all(r["cause"] and r["check"] for r in rows), (m, ct.key)
    for sp in specials():
        assert all(len(r["checks"]) >= 2 for r in load_special(sp).rules), sp


def test_guidance_lists_checks_in_the_order_the_changes_began_and_claims_no_cause(eq):
    g = guide(eq)
    assert [(i.system, i.title) for i in g.items] == [
        ("주 구동부", "부하 증가"), ("유압 공급 라인", "유로 저항 증가"), ("동작 사이클", "사이클 지연"), ("동작 사이클", "구간 동작 지연"),
        ("유압 공급 라인", "유량 감소"), ("주 구동부", "진동 증가")]
    assert all(i.kind == "common" and i.candidates for i in g.items) and g.items[0].start == 1200.0
    a = g.answer
    assert a.value("guide_items") == 6 and a.value("guide_special_items") == 0 and a.confidence.level == "low"
    assert "원인을 판정한 것이 아님" in a.basis[1] and a.basis[2].startswith("1. [주 구동부] 부하 증가 (current, 1200부터)")
    quiet = guide(diagnose_equipment([{**SPINDLE, "current": syn.drive(2000, seed=43)}]))
    assert quiet.items == () and quiet.answer.basis[-1] == "이상 징후가 없어 점검할 항목이 없음"


def test_special_finding_replaces_the_common_checks_for_the_same_change():
    cut = diagnose_equipment([{**SPINDLE, "current": syn.inject(syn.drive(2000, seed=42), "current", 1400, 2000, -1.6)}])
    (common,) = guide(cut).items
    assert (common.title, common.kind) == ("부하 감소", "common") and common.candidates[0].cause.startswith("실제 부하가 줄었다")
    (special,) = guide(cut, interpret("cutting", cut)).items
    assert (special.title, special.kind) == ("공구 파손 의심", "special")
    assert special.candidates[0].check == "공구 날의 파손 여부를 눈으로 확인" and special.candidates[0].cause == ""
    ans = packs.get("diagnosis").solve({"task": "guide", "special": "cutting", "systems": [
        {**SPINDLE, "current": syn.inject(syn.drive(2000, seed=42), "current", 1400, 2000, -1.6)}]})
    assert ans.value("guide_special_items") == 1 and ans.inputs["special"] == "cutting"


def test_trend_shows_when_each_system_left_normal_and_which_came_first(eq):
    t = trend(eq)
    assert t.windows == 12 and t.order == ("주 구동부", "유압 공급 라인", "동작 사이클")
    by = {s.name: s for s in t.systems}
    assert by["가열 구역"].direction == "normal" and by["가열 구역"].first_window is None and not by["가열 구역"].fraction.any()
    drive = by["주 구동부"]
    assert drive.first_window == 7 and not drive.fraction[:7].any() and drive.fraction[8] == 1.0 and drive.direction == "worsening"
    assert drive.peak[8] > 4 > drive.peak[0]
    early = diagnose_equipment([{**SPINDLE, "current": syn.inject(syn.drive(2000, seed=42), "current", 100, 500, 1.0)}])
    assert trend(early, windows=4).systems[0].direction == "easing" and np.allclose(trend(early, windows=4).systems[0].fraction[2:], 0)
    with pytest.raises(ValueError):
        trend(eq, windows=1)


def test_questions_about_cause_or_checks_get_the_checks_for_what_they_point_at(eq):
    g = guide(eq)
    r = ask("유압 쪽은 무엇을 점검해야 하나요?", eq, guidance=g)
    assert "원인은 판정하지 않았습니다" in r.text and "필터 오염 상태와 교체 주기 확인" in r.text and "주 구동부" not in r.text
    assert "원인 후보와 확인할 것" in r.facts
    v = ask("구동부 진동이 왜 커졌나요?", eq, guidance=g).text
    assert "볼트 체결 상태 확인" in v and "윤활 상태" not in v                 # 진동의 점검만, 전류(부하 증가)의 점검은 아님
    assert "점검" not in ask("이 설비 지금 어떤가요?", eq, guidance=g).text          # 묻지 않으면 붙이지 않는다
    assert "공통 진단은 무엇이 어떻게" in ask("구동부 진동이 왜 커졌나요?", eq).text   # 안내가 없으면 예전 답


def test_screen_and_server_carry_trend_guidance_and_site_special(tmp_path, eq):
    g = guide(eq)
    page = render_equipment(eq, guidance=g, trend=trend(eq))
    assert "상태 추이" in page and "원인 후보와 점검 안내" in page and page.count('class="guide"') == 6 and "http" not in page
    assert page.count("<svg") == 14 and "이상이 시작된 순서: 주 구동부 → 유압 공급 라인 → 동작 사이클" in page
    plain = render_equipment(eq)
    assert "상태 추이" not in plain and "원인 후보와 점검 안내" not in plain

    def write(name, data):
        keys = list(data)
        (tmp_path / name).write_text(",".join(keys) + "\n" + "\n".join(",".join(repr(float(data[k][i])) for k in keys)
                                     for i in range(len(data[keys[0]]))), encoding="utf-8")
    write("n.csv", syn.drive(1500, seed=41)); write("c.csv", syn.inject(syn.drive(800, seed=42), "current", 500, 800, -1.6))
    site = tmp_path / "site.yaml"
    site.write_text("equipment: 5호기\nspecial: cutting\nsystems:\n  - name: 주축\n    module: drive\n    normal: n.csv\n    current: c.csv\n"
                    "    time: t\n    signals: {current: current}\n    conditions: {load: load, speed: speed}\n", encoding="utf-8")
    assert site_special(site) == "cutting"
    out = tmp_path / "r.html"
    demo_main(["--site", str(site), "--out", str(out)])
    html_text = out.read_text(encoding="utf-8")
    assert all(t in html_text for t in ("공구 파손 의심", "이 공정에서의 뜻", "원인 후보와 점검 안내", "상태 추이", "특화 해석"))
    srv = make_server(eq, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        assert "원인 후보와 점검 안내" in urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        req = urllib.request.Request(base + "/ask", data=json.dumps({"question": "사이클은 뭘 확인해야 하나요?"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        assert "구간별 동작 시간에서 늘어난 구간 확인" in json.loads(urllib.request.urlopen(req, timeout=5).read())["text"]
    finally:
        srv.shutdown(); srv.server_close()
