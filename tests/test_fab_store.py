"""ConT FAB 고르기: 목록에는 실제로 있는 엔진만, 샘플은 엔진을 돌린 결과, 묶어서 진열하고, 고른 것은 파일로."""
import json
import os
import re
import threading
import urllib.request

import pytest

from cont.dialogue.serve_fastening import example
from cont.fab.catalog import catalog, load, make, selection
from cont.fab.previews import MAKEABLE, PREVIEWS, joint_for
from cont.fab.store import COMPARE_MAX, main, make_server, render_store
from cont.packs.fastening.pack import answer
from cont.view.iso_svg import iso_svg


@pytest.fixture(scope="module")
def items():
    return catalog()


def test_catalog_lists_only_engines_that_exist_and_groups_them_by_form_and_by_physical_quantity(items):
    data = load()
    keys = [i["key"] for i in data["items"]]
    assert len(keys) == len(set(keys)) >= 24 and all(i["preview"] in PREVIEWS for i in data["items"])
    assert set(data["forms"]) == {"image", "graph", "3d", "4d", "video", "signal", "number", "judge"}
    assert {i["form"] for i in data["items"]} == set(data["forms"])                       # 형태마다 고를 것이 하나는 있다
    assert {i["quantity"] for i in data["items"]} == set(data["quantities"])              # 물리 특성마다도 하나는 있다
    assert sum(i["form"] == "image" for i in data["items"]) >= 6 and sum(i["form"] == "graph" for i in data["items"]) >= 8      # 서로 다른 그림이 여러 가지다
    assert all(i["uses"] and set(i["uses"]) <= set(data["uses"]) and i["limits"] for i in data["items"])
    assert all(set(s["items"]) <= set(keys) and len(s["items"]) >= 2 for s in data["sets"]) and len(data["sets"]) >= 3
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert all(os.path.exists(os.path.join(root, i["doc"])) for i in data["items"] if i.get("doc"))
    assert [i["key"] for i in items] == keys


def test_each_product_has_samples_made_by_running_the_engine(items):
    by = {i["key"]: i for i in items}
    assert sum(len(i["samples"]) for i in items) >= 80 and all(s["html"].strip() and s["facts"] and s["label"] for i in items for s in i["samples"])
    assert len(by["fastening_shape"]["samples"]) == 7 and len({s["label"] for s in by["fastening_shape"]["samples"]}) == 7      # 규격마다 다른 3D
    assert all(s["html"].startswith("<svg") and s["html"].count("<path") > 100 for s in by["fastening_shape"]["samples"])
    pictures = {k: by[k]["samples"][0]["html"] for k in ("fastening_field", "field_mises", "field_radial", "field_shear", "field_displacement")}
    assert len(set(pictures.values())) == 5 and all(v.startswith("<svg") for v in pictures.values())      # 물리량이 다르면 그림이 다르다
    assert {by[k]["quantity"] for k in ("signal_drive", "signal_pressure", "signal_thermal", "signal_cycle")} == {"전류 · 진동", "압력 · 유량", "온도", "시간 · 사이클"}
    assert all(len(by[k]["samples"]) >= 3 for k in ("signal_drive", "signal_pressure", "signal_thermal", "signal_cycle"))
    assert len(by["guidance"]["samples"]) >= 6 and len(by["cutting_force"]["samples"]) == 6 and len(by["cutting_curve"]["samples"]) == 2
    assert by["fastening_process"]["samples"][0]["html"].count("<figure>") == load()["rule"]["process_frames"]
    f = joint_for("M12")                                                                    # 샘플의 숫자는 그 조건으로 계산한 값이다
    a = answer(f["joint"], f["load"])
    s = next(x for x in by["fastening_diagram"]["samples"] if x["params"]["size"] == "M12")
    assert ["조립 체결력", f"{a.value('preload'):,.0f} N"] in s["facts"] and a.value("safety_yield") >= load()["rule"]["yield_safety"] - 1e-9
    from cont.packs.fastening.field import stress_field
    fa = stress_field(f["joint"], f["load"])
    s = next(x for x in by["interface_pressure"]["samples"] if x["params"]["size"] == "M12")
    assert ["최대 압력", f"{fa.value('interface_peak_pressure'):,.0f} MPa"] in s["facts"]
    assert all(i["makeable"] == (load()["items"][n]["preview"] in MAKEABLE) for n, i in enumerate(items))


def test_field_engine_gives_several_physical_quantities():
    from cont.packs.fastening.field import stress_field
    j, l = example()
    a = stress_field(j, l)
    fields = {f.key: f for f in a.fields}
    assert set(fields) == {"plate_axial_compression", "plate_von_mises", "plate_radial_compression", "plate_shear", "plate_axial_displacement"}
    assert fields["plate_axial_displacement"].unit == "µm" and min(v for row in fields["plate_shear"].values for v in row if v is not None) >= 0
    assert len({(len(f.x), len(f.y)) for f in a.fields}) == 1                               # 같은 격자 위의 값들이다


def test_iso_svg_draws_the_real_mesh_and_colours_the_bolt_by_use():
    j, l = example()
    from cont.view.fastening_live import state
    v = state(j, l, answer(j, l))["viewer"]
    plain, hot = iso_svg(v), iso_svg(v, use=1.0)
    assert plain.startswith("<svg") and plain.count("<path") > 200 and plain != hot and iso_svg(v, use=0.0) != hot
    assert iso_svg(v, hidden=True).count("<path") > plain.count("<path") and 'opacity="0.2"' in iso_svg(v, hidden=True)   # 숨은 물리: 판을 비쳐 그린다


def test_engine_makes_a_new_sample_on_request():
    s = make("fastening_diagram", {"size": "m16", "torque": 120})
    f = joint_for("M16", 120.0)
    assert s["label"] == "M16 · 120 N·m" and ["조립 체결력", f"{answer(f['joint'], f['load']).value('preload'):,.0f} N"] in s["facts"]
    assert make("fastening_shape", {"size": "M8"})["params"]["size"] == "M8"                # 토크를 비우면 추천 엔진이 고른다
    for bad in (("signal_drive", {"size": "M10"}), ("fastening_field", {"size": "M7"}), ("fastening_field", {"size": "M10", "torque": -1})):
        with pytest.raises(ValueError):
            make(*bad)


def test_selection_is_the_seed_of_my_fab():
    s = selection(["fastening_field", "guidance", "fastening_field"], site="가상 라인")
    assert s["format"] == "cont-fab-selection" and s["site"] == "가상 라인" and [i["key"] for i in s["items"]] == ["fastening_field", "guidance"]
    with pytest.raises(ValueError):
        selection(["no_such_engine"])


def test_store_page_is_a_shop_with_shelves_details_compare_and_my_fab_bar(items, tmp_path):
    page = render_store(items)
    assert page.startswith("<!DOCTYPE html>") and all(x in page for x in (
        "ConT FAB", "고르기", "내 Fab을 꾸리세요", 'id="q"', 'id="shelves"', 'id="detail"', 'id="cmp"', "견주기", "함께 담으면 좋은 것", "내 Fab", "구성 화면 열기", "내려받기",
        "세트 담기", "prefers-reduced-motion", 'data-grp="form"', 'data-grp="quantity"', "물리 특성별", "data-var"))
    assert "계산값 · 검증 전" in page and "실측과 대조하기 전" in page
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", page, flags=re.S)
    assert not re.search(r"\d\s*(만\s*)?원|USD|\$\d|€", text)                              # 가격이 없다
    data = json.loads(re.search(r'id="store-data">(.*?)</script>', page, re.S).group(1))
    assert [i["key"] for i in data["items"]] == [i["key"] for i in items] and data["make_url"] is None and data["compare_max"] == COMPARE_MAX and data["quantities"] == load()["quantities"]
    assert [f[0] for f in data["forms"]] == list(load()["forms"]) and len(data["sets"]) == len(load()["sets"])
    live = page[page.index('id="live"'):page.index('id="livecap"')]
    assert len(data["hero"]["caps"]) == live.count("<svg") >= 4 and "N·m →" in data["hero"]["caps"][0]      # 맨 위 장면은 엔진이 만든 것
    out = tmp_path / "fab.html"
    main(["--out", str(out)])
    assert 'id="store-data"' in out.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        render_store([])


def test_server_makes_samples_on_request_and_says_why_when_it_cannot():
    srv = make_server(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(body):
        req = urllib.request.Request(base + "/make", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    try:
        assert '"make_url":"/make"' in urllib.request.urlopen(base + "/", timeout=10).read().decode("utf-8")
        ok = post({"key": "fastening_torque", "size": "M12", "torque": "70"})
        assert ok["label"] == "M12 · 70 N·m" and ok["html"].startswith("<svg")
        assert "만들지 못했습니다" in post({"key": "fastening_torque", "size": "M7", "torque": ""})["error"]
        assert "만들지 못했습니다" in post({"key": "guidance", "size": "M10"})["error"]
    finally:
        srv.shutdown(); srv.server_close()


def test_card_is_short_and_detail_is_full():
    items = catalog()
    assert all(0 < len(i["short"]) <= 24 for i in items)            # 카드에는 한 줄 설명만
    assert all(i["short"] != i["summary"] for i in items)           # 긴 설명은 상세 창에서


def test_filters_are_compact_menus_in_the_top_bar_and_the_bar_hides_while_scrolling_down():
    from cont.fab.catalog import catalog, load
    page = render_store(catalog(), load(), "")
    top = page[page.index('<header class="top">'):page.index("</header>")]
    assert top.count('class="dd"') == 4 and all(w in top for w in ("묶기", "형태", "쓰임", "물리 영역", 'data-grp="quantity"', 'data-area="체결"'))
    assert 'class="filters"' not in page and "classList.add('away')" in page            # 줄마다 펼친 칩 대신 작은 메뉴, 내려가면 막대가 숨는다


def test_samples_carry_what_the_detail_preview_needs_to_be_operated():
    from cont.fab.catalog import catalog, meshes
    items = {i["key"]: i for i in catalog()}
    for key in ("fastening_shape", "fastening_hidden"):                                   # 3D: 돌려 볼 자료
        assert all(s["view3d"]["size"] in s["label"] for s in items[key]["samples"])
    assert all(s["view3d"]["hidden"] for s in items["fastening_hidden"]["samples"]) and not any(s["view3d"]["hidden"] for s in items["fastening_shape"]["samples"])
    m = meshes(list(items.values()))
    assert set(m) == {s["view3d"]["size"] for s in items["fastening_shape"]["samples"]} and all(v["p"] and v["r"] > 0 for v in m.values())
    for key in ("fastening_process", "fastening_video"):                                  # 4D·영상: 재생할 장면 여러 장
        assert all(s["html"].count("<figure>") >= 4 for s in items[key]["samples"])
    for s in items["guidance"]["samples"]:                                                # 판단·점검: 근거(관찰·후보·점검)와 번호
        assert all(re.search(p, s["more"]) for p in (r"E-\d\d", r"H-\d\d", r"M-\d\d", "확정이 아닙니다"))
    assert all("추천하는 측정 단계 전부" in s["more"] for s in items["fastening_sensing"]["samples"])


def test_my_fab_keeps_the_condition_and_view_and_can_be_reopened():
    from cont.fab.catalog import catalog, load
    page = render_store(catalog(), load(), "")
    for w in ('id="build"', "cont-fab-selection", "version:2", "localStorage", 'id="b-file"', "data-v3", 'data-pl="play"', "연결 정보만 적음, 실제 연결은 아직 없음", "구성 화면 열기"):
        assert w in page
    assert "다음: 꾸리기 (준비 중)" not in page and "picked=[" not in page                       # 이름만 담던 옛 목록이 남지 않았다
    assert "condition:{label:p.label,params:p.params}" in page and "view:p.view" in page      # 조건과 보던 설정을 함께 저장한다


# ---- 표현 유형 (엔진 없는 유형은 준비 중 카드) ----
def test_types_counts_and_rules():
    from cont.fab.catalog import types_data
    from cont.fab.sketches import NOTE, SKETCHES
    d = types_data(); ts = d["types"]
    assert len(ts) == 59
    open_ = [t for t in ts if not t["covered_by"]]
    assert len(open_) == 37
    assert len({t["key"] for t in ts}) == 59
    for t in open_:
        assert t["engine"] in d["engines"] and t["ready"] and t["needs"]
        assert NOTE in t["sketch_svg"] and "viewBox" in t["sketch_svg"]
    assert {t["sketch_svg"] and 1 for t in ts if t["covered_by"]} == {None} or all(t["sketch_svg"] == "" for t in ts if t["covered_by"])
    assert len(SKETCHES) >= 38


def test_types_validation_rejects_unknown_engine(monkeypatch):
    import cont.fab.catalog as c
    raw = c._types_yaml()
    bad = {"engines": raw["engines"], "types": [dict(raw["types"][1], engine="nope")]}
    monkeypatch.setattr(c, "_types_yaml", lambda: bad)
    import pytest
    with pytest.raises(ValueError):
        c.types_data()


def test_store_type_cards_and_requests():
    from cont.fab.catalog import catalog
    from cont.fab.store import render_store
    page = render_store(catalog())
    assert "준비 중 · 엔진 없음" in page and "필요해요" in page and "예시 그림 · 실제 결과 아님" in page
    assert "kind:'engine_request'" in page and "requests:reqs" in page
    assert 'id="tdetail"' in page and "확장 예정 (엔진이 없는 것)" in page
    assert "data-req" in page and "tcard" in page


def test_usable_results_come_before_coming_soon_and_soon_cards_have_no_run_button():
    """첫 화면: 지금 쓸 수 있는 세트와 결과가 앞, 엔진 없는 카드는 '확장 예정' 안에 있고 담기·실행 단추가 없다."""
    from cont.fab.catalog import catalog
    from cont.fab.store import render_store
    page = render_store(catalog())
    build = page[page.index("function build(){"):page.index("$('#shelves').innerHTML=h;}")]
    assert build.index("data-set=") < build.index("card(it,0)") < build.index('id="soon"') < build.index("tcard")
    tcard = page[page.index("function tcard("):page.index("function build(")]
    assert "data-add" not in tcard and "data-set" not in tcard and "필요해요" in tcard

def test_set_condition_uses_a_common_size_that_really_exists_and_flags_mixed_sets():
    from cont.fab.catalog import catalog, load, set_condition
    items, sets = catalog(), {s["key"]: s for s in load()["sets"]}
    by = {i["key"]: i for i in items}
    c = set_condition(items, sets["set_fastening"])
    assert c["mode"] == "common" and "M10" in c["note"]
    for k, idx in c["pick"].items():                                   # 고른 조건은 그 상품에서 실제로 계산해 둔 샘플이다
        assert by[k]["samples"][idx]["params"]["size"] == "M10"
    assert set_condition(items, sets["set_monitor"])["mode"] == "none"
    fake = [{"key": "a", "name": "가", "samples": [{"label": "M6 · 1", "params": {"size": "M6"}}]},
            {"key": "b", "name": "나", "samples": [{"label": "M16 · 2", "params": {"size": "M16"}}]}]
    m = set_condition(fake, {"items": ["a", "b"]})
    assert m["mode"] == "mixed" and "비교용" in m["note"] and "M6 · 1" in m["note"] and "M16 · 2" in m["note"]


def test_set_button_adds_picks_at_the_common_condition_and_says_so():
    from cont.fab.catalog import catalog
    from cont.fab.store import render_store
    page = render_store(catalog())
    assert 'id=\\"setnote\\"' in page or 'id="setnote"' in page
    assert "st.condition" in page and "pk[k]||0" in page and "setcond" in page


def test_3d_samples_keep_a_static_view_so_the_screen_is_never_blank_without_3d():
    """3D를 못 쓰면(그리는 곳이 없거나 자료가 비면) 대표 단면(정적 그림)과 안내가 남는다 (X3)."""
    html = render_store(catalog(), load(), "")
    assert "3D를 쓸 수 없어 대표 단면으로 보여 드립니다" in html
    assert "function no3(" in html and "can2()" in html
    data = json.loads(re.search(r'id="store-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    shown = [(it, s) for it in data["items"] for s in it["samples"] if s.get("view3d")]
    assert shown
    for it, s in shown:
        assert s["html"].strip() and it["name"] and s["label"]


def test_mode_banner_tells_static_demo_from_live_and_late_results_stay_on_the_asked_item():
    """공개 시연과 실시간 작업이 구분되고, 늦게 온 결과는 요청한 상품에만 더해진다 (X4)."""
    static = render_store(catalog(), load(), "")
    live = render_store(catalog(), load(), "/make", "/analyze")
    assert "공개 시연: 미리 계산한 샘플만" in static and "실시간 작업 가능" not in static.split('id="mode"')[1].split("</p>")[0]
    assert "실시간 작업 가능: 규격" in live and "공개 시연:" not in live.split('id="mode"')[1].split("</p>")[0]
    assert "asked=cur" in live and "지금 보는 상품에는 반영하지 않았습니다" in live
