import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from cont.objspec import ObjectSpecError, ViewState, hybrid_bonding_stack
from cont.objspec.scene import Timeline, load_playback
from cont.view.scene4d import POSE_JS, SCENE_JS, scene4d, scene4d_page, scene_data

S = hybrid_bonding_stack()


def test_timeline_stages_are_consecutive_and_use_config_base():
    tl = Timeline(S)
    base = load_playback()["stage_base_seconds"]
    assert [g.stage_id for g in tl.segments] == ["approach", "align", "contact"]
    assert tl.segments[0].t0 == 0 and all(a.t1 == b.t0 for a, b in zip(tl.segments, tl.segments[1:]))
    assert tl.duration == pytest.approx(3 * base)


def test_poses_follow_stage_end_poses_and_start_at_start_pose():
    tl = Timeline(S)
    start = tl.pose_at(0)
    assert start["die.si"].dz == 4.0 and start["die.si"].dx == 1.0 and start["wafer.si"].dz == 0.0
    ends = [tl.pose_at(g.t1)["die.si"] for g in tl.segments]
    assert [(p.dz, p.dx) for p in ends] == [(2.0, 1.0), (2.0, 0.0), (0.0, 0.0)]
    assert tl.pose_at(-5) == tl.pose_at(0) and tl.pose_at(999) == tl.pose_at(tl.duration)   # 범위 밖은 끝으로 자른다


def test_motion_is_monotonic_inside_a_stage_and_untouched_parts_stay():
    tl = Timeline(S)
    xs = [tl.pose_at(tl.segments[1].t0 + i * 0.1)["die.si"].dx for i in range(21)]
    assert all(a >= b for a, b in zip(xs, xs[1:])) and xs[0] == 1.0 and xs[-1] == 0.0
    assert all(tl.pose_at(t)["wafer.dielectric"].dz == 0 for t in (0, 1, 3, 6))


def test_speed_of_one_stage_changes_only_that_stage_length():
    slow = Timeline(S, ViewState().with_speed(S, 2, 0.5))
    base = Timeline(S)
    assert slow.segments[1].t1 - slow.segments[1].t0 == pytest.approx(2 * (base.segments[1].t1 - base.segments[1].t0))
    assert slow.segments[0].t1 - slow.segments[0].t0 == base.segments[0].t1 - base.segments[0].t0
    assert slow.segments[2].t1 - slow.segments[2].t0 == base.segments[2].t1 - base.segments[2].t0
    assert slow.duration == pytest.approx(base.duration + 2.0)
    # 끝 자세는 속도와 무관하다 (값은 그대로, 재생만 느려진다)
    assert slow.pose_at(slow.duration) == base.pose_at(base.duration)


def test_stage_reference_by_ordinal_id_or_name():
    assert S.stage(2).id == "align" and S.stage("align").id == "align" and S.stage("정렬").id == "align"
    for bad in (0, 4, -1, "없는단계", True):
        with pytest.raises(ObjectSpecError):
            S.stage(bad)
    assert ViewState().with_speed(S, "정렬", 0.5).speed_of("align") == 0.5


def test_boundary_time_belongs_to_next_stage_and_end_to_last():
    tl = Timeline(S)
    assert tl.segment_at(tl.segments[0].t1).stage_id == "align" and tl.segment_at(tl.duration).stage_id == "contact"


def test_scene_data_carries_ids_camera_and_timeline_without_structure_change():
    v = ViewState().with_camera(azimuth=120.0).with_speed(S, 2, 0.5)
    a, b = scene_data(S), scene_data(S, v)
    assert [p["id"] for p in a["parts"]] == list(S.part_ids)
    assert a["spec_version"] == b["spec_version"] == S.version
    assert [p["tri"] for p in a["parts"]] == [p["tri"] for p in b["parts"]]        # 카메라·속도로 모양은 다시 만들지 않는다
    assert a["camera"] != b["camera"] and a["timeline"]["duration"] < b["timeline"]["duration"]


def test_editing_a_part_changes_only_that_parts_mesh_and_version():
    n = S.edit_part("die.si", z1=2.4)
    a, b = scene_data(S), scene_data(n)
    assert a["spec_version"] != b["spec_version"]
    diff = [x["id"] for x, y in zip(a["parts"], b["parts"]) if x["tri"] != y["tri"]]
    assert diff == ["die.si"]


def test_html_has_ids_note_and_escapes_script_end():
    h = scene4d(S)
    assert 'data-part-id="die.si"' in h and "물리 시간이 아닙니다" in h and "설명용 값" in h
    spec = S.edit_part("die.si", name="</script><b>x")
    h2 = scene4d(spec)
    assert "</script><b>x" not in h2 and h2.count("</script>") == 1
    assert json.loads(re.search(r'<script type="application/json">(.*?)</script>', h2, re.S).group(1).replace("<\\/", "</"))


def _node():
    return shutil.which("node")


@pytest.mark.skipif(_node() is None, reason="node가 없으면 JS 점검을 건너뛴다")
def test_js_has_valid_syntax_and_matches_python_poses():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "scene.js"
        f.write_text(SCENE_JS, encoding="utf-8")
        assert subprocess.run([_node(), "--check", str(f)], capture_output=True).returncode == 0
        for view in (ViewState(), ViewState().with_speed(S, 2, 0.5).with_speed(S, 3, 2.0)):
            tl = Timeline(S, view)
            ts = [0, 0.4, 1.0, tl.segments[1].t0, 3.3, tl.segments[2].t0, 5.0, tl.duration]
            js = POSE_JS + f"var T={json.dumps(tl.to_dict())};var out={{}};" + \
                f"{json.dumps(ts)}.forEach(function(t,k){{out[k]=T.part_ids.map(function(i){{return poseAt(T,t,i)}})}});console.log(JSON.stringify(out));"
            r = subprocess.run([_node(), "-e", js], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
            got = json.loads(r.stdout)
            for k, t in enumerate(ts):
                want = tl.pose_at(t)
                for pid, (dz, dx) in zip(tl.spec.part_ids, got[str(k)]):
                    assert dz == pytest.approx(want[pid].dz, abs=1e-9) and dx == pytest.approx(want[pid].dx, abs=1e-9)


def _chrome():
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


@pytest.mark.skipif(_chrome() is None, reason="Chrome이 없으면 브라우저 점검을 건너뛴다")
def test_page_renders_and_plays_in_a_real_browser(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    page = tmp_path / "scene.html"
    page.write_text(scene4d_page(S, ViewState().with_camera(azimuth=120.0)), encoding="utf-8")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(executable_path=_chrome(), args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 800, "height": 700})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(page.as_uri())
        try:
            pg.wait_for_selector("canvas[data-ready='1']", timeout=8000)
        except Exception:
            if "3D 보기를 쓸 수 없습니다" in pg.inner_text(".msg"):
                pytest.skip("이 환경의 브라우저에는 WebGL이 없다")
            raise
        pg.click(".stage[data-i='2']")
        assert "단계 3/3 접촉" in pg.inner_text(".info")
        pg.click(".stage[data-i='0']")
        pg.click(".play")
        pg.wait_for_timeout(300)
        assert "단계 1/3 접근" in pg.inner_text(".info") and pg.inner_text(".play") == "멈춤"
        b.close()
    assert errors == []


def test_start_time_is_carried_into_the_scene_data_and_clamped():
    assert scene_data(S, start_t=3.2)["start_t"] == 3.2
    h = scene4d(S, start_t=99.0)
    assert 'value="6.0"' in h                     # 끝을 넘으면 끝으로 자른다
    assert 'value="2.5"' in scene4d(S, start_t=2.5)


@pytest.mark.skipif(_chrome() is None, reason="Chrome이 없으면 브라우저 점검을 건너뛴다")
def test_reopened_project_scene_starts_at_saved_position(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    from cont.service.project import open_project, save_project
    view = ViewState().with_camera(azimuth=100.0).with_speed(S, 2, 0.5)
    save_project(tmp_path / "proj", "p1", "본딩", S, view, ("die.si",), 3.2)
    o = open_project(tmp_path / "proj")
    page = tmp_path / "scene.html"
    page.write_text(scene4d_page(o.state.spec, o.state.view, start_t=o.state.playback_t), encoding="utf-8")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(executable_path=_chrome(), args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 800, "height": 700})
        pg.goto(page.as_uri())
        try:
            pg.wait_for_selector("canvas[data-ready='1']", timeout=8000)
        except Exception:
            if "3D 보기를 쓸 수 없습니다" in pg.inner_text(".msg"):
                pytest.skip("이 환경의 브라우저에는 WebGL이 없다")
            raise
        info = pg.inner_text(".info")
        b.close()
    assert "설명용 재생 3.2/8.0 s" in info and "단계 2/3 정렬" in info and "속도 0.5배" in info


# ---- 부품 선택 ----------------------------------------------------------------------------------------------------
def test_selection_is_validated_deduplicated_and_rendered_as_pressed_buttons():
    assert scene_data(S, selection=["die.si", "die.si", "wafer.si"])["selection"] == ["die.si", "wafer.si"]
    with pytest.raises(ObjectSpecError, match="명세에 없는 부품"):
        scene_data(S, selection=["없는부품"])
    h = scene4d(S, selection=["die.si"])
    assert re.search(r'<button type="button" class="key" data-part-id="die.si" aria-pressed="true">', h)
    assert re.search(r'data-part-id="wafer.si" aria-pressed="false"', h)
    assert scene_data(S)["selection"] == [] and "s4d:select" in SCENE_JS and "s4dSelect" in SCENE_JS


def _launch(sync_api, p):
    return p.chromium.launch(executable_path=_chrome(), args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])


def _open_scene(pg, tmp_path, html_text):
    f = tmp_path / "scene.html"
    f.write_text(html_text, encoding="utf-8")
    pg.goto(f.as_uri())
    try:
        pg.wait_for_selector("canvas[data-ready='1']", timeout=8000)
    except Exception:
        if "3D 보기를 쓸 수 없습니다" in pg.inner_text(".msg"):
            pytest.skip("이 환경의 브라우저에는 WebGL이 없다")
        raise
    pg.evaluate("window.__ev=[];document.querySelector('.s4d').addEventListener('s4d:select',function(e){window.__ev.push(e.detail);});")


def _click_at(pg, part_id, modifiers=()):
    """부품의 투영 중심을 눌러 본다(투영식은 화면 코드가 갖고 있고, 어느 부품인지는 따로 그린 화면에서 읽는다)."""
    x, y = pg.evaluate(f"document.querySelector('.s4d').s4dProject({part_id!r})")
    box = pg.locator("canvas").bounding_box()
    for m in modifiers:
        pg.keyboard.down(m)
    try:
        pg.mouse.click(box["x"] + x, box["y"] + y)
    finally:
        for m in modifiers:
            pg.keyboard.up(m)


@pytest.mark.skipif(_chrome() is None, reason="Chrome이 없으면 브라우저 점검을 건너뛴다")
def test_clicking_a_part_selects_it_and_reports_ids_with_the_spec_version(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    view = ViewState().with_camera(azimuth=30.0, elevation=0.0)                  # 옆에서 보면 층마다 띠로 보여 서로 가리지 않는다
    with sync_api.sync_playwright() as p:
        b = _launch(sync_api, p)
        pg = b.new_page(viewport={"width": 800, "height": 700})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _open_scene(pg, tmp_path, scene4d_page(S, view, start_t=6.0))             # 접촉 단계 끝: 모두 쌓인 상태
        for pid in ("wafer.si", "wafer.dielectric", "die.dielectric", "die.si"):
            _click_at(pg, pid)
            assert pg.evaluate("document.querySelector('.s4d').dataset.selected") == pid, pid
            assert pg.evaluate("window.__ev.slice(-1)[0]") == {"ids": [pid], "spec_version": S.version, "source": "canvas"}
            assert f"선택: {S.part(pid).part.name}" in pg.inner_text(".info")
            assert pg.get_attribute(f".key[data-part-id='{pid}']", "aria-pressed") == "true"
        n = pg.evaluate("window.__ev.length")
        _click_at(pg, "die.si")                                                   # 이미 그것만 선택돼 있으면 바뀐 것이 없으므로 알리지 않는다
        assert pg.evaluate("window.__ev.length") == n
        pg.mouse.click(*[pg.locator("canvas").bounding_box()[k] + 6 for k in ("x", "y")])      # 빈 곳
        assert pg.evaluate("document.querySelector('.s4d').dataset.selected") == ""
        assert pg.evaluate("window.__ev.slice(-1)[0]['ids']") == []
        b.close()
    assert errors == []


@pytest.mark.skipif(_chrome() is None, reason="Chrome이 없으면 브라우저 점검을 건너뛴다")
def test_shift_click_adds_and_removes_and_legend_buttons_select_too(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        b = _launch(sync_api, p)
        pg = b.new_page(viewport={"width": 800, "height": 700})
        _open_scene(pg, tmp_path, scene4d_page(S, ViewState().with_camera(azimuth=30.0, elevation=0.0), start_t=6.0))
        sel = lambda: pg.evaluate("document.querySelector('.s4d').dataset.selected")
        _click_at(pg, "die.si")
        _click_at(pg, "wafer.si", modifiers=["Shift"])
        assert sel() == "die.si,wafer.si"
        _click_at(pg, "die.si", modifiers=["Shift"])
        assert sel() == "wafer.si"
        pg.click(".key[data-part-id='die.dielectric']")                           # 범례 단추(키보드로도 누를 수 있다)
        assert sel() == "die.dielectric" and pg.evaluate("window.__ev.slice(-1)[0]['source']") == "legend"
        pg.click(".key[data-part-id='wafer.dielectric']", modifiers=["Control"])
        assert sel() == "die.dielectric,wafer.dielectric"
        b.close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome이 없으면 브라우저 점검을 건너뛴다")
def test_dragging_rotates_without_selecting_and_hidden_parts_are_not_picked(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        b = _launch(sync_api, p)
        pg = b.new_page(viewport={"width": 800, "height": 700})
        _open_scene(pg, tmp_path, scene4d_page(S, ViewState().with_camera(azimuth=30.0, elevation=0.0), start_t=6.0))
        before = pg.evaluate("document.querySelector('.s4d').s4dProject('die.si')")
        x, y = before
        box = pg.locator("canvas").bounding_box()
        pg.mouse.move(box["x"] + x, box["y"] + y)
        pg.mouse.down()
        pg.mouse.move(box["x"] + x + 60, box["y"] + y + 30, steps=5)
        pg.mouse.up()
        assert pg.evaluate("document.querySelector('.s4d').dataset.selected") == "" and pg.evaluate("window.__ev.length") == 0   # 끌기는 선택이 아니다
        assert pg.evaluate("document.querySelector('.s4d').s4dProject('die.si')") != before                                   # 시점은 돌았다
        pg.evaluate("document.querySelector('.s4d .cam').click()")
        x, y = pg.evaluate("document.querySelector('.s4d').s4dProject('die.si')")
        still = pg.evaluate("document.querySelector('.s4d').s4dProject('die.si')")
        pg.mouse.move(box["x"] + x, box["y"] + y)
        pg.mouse.down()
        pg.mouse.move(box["x"] + x + 3, box["y"] + y + 2)                                                                   # 손이 조금 떨린 클릭은 돌리지 않고 선택한다
        pg.mouse.up()
        assert pg.evaluate("document.querySelector('.s4d').dataset.selected") == "die.si"
        assert pg.evaluate("document.querySelector('.s4d').s4dProject('die.si')") == still
        pg.evaluate("document.querySelector('.s4d').s4dSelect([])")
        pg.keyboard.press("ArrowDown")                                                                                      # 키보드 회전 뒤 위에서 보기
        for _ in range(7):
            pg.keyboard.press("ArrowDown")
        # 거의 위에서 본 상태: 위 다이가 아래 웨이퍼의 중심을 가린다 -> 눌러도 가려진 웨이퍼가 아니라 보이는 위 다이가 선택된다
        _click_at(pg, "wafer.si")
        assert pg.evaluate("document.querySelector('.s4d').dataset.selected") in ("die.si", "die.dielectric")
        b.close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome이 없으면 브라우저 점검을 건너뛴다")
def test_initial_selection_and_s4dSelect_highlight_without_emitting_and_ignore_unknown_ids(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    PIL_Image = pytest.importorskip("PIL.Image")
    import io
    view = ViewState().with_camera(azimuth=30.0, elevation=0.0)
    with sync_api.sync_playwright() as p:
        b = _launch(sync_api, p)
        pg = b.new_page(viewport={"width": 800, "height": 700})
        _open_scene(pg, tmp_path, scene4d_page(S, view, start_t=6.0, selection=["die.si"]))
        assert pg.evaluate("document.querySelector('.s4d').dataset.selected") == "die.si"       # 저장된 선택을 처음부터 보여 준다

        def color(pid):
            x, y = pg.evaluate(f"document.querySelector('.s4d').s4dProject({pid!r})")
            box = pg.locator("canvas").bounding_box()
            im = PIL_Image.open(io.BytesIO(pg.screenshot(clip={"x": box["x"] + x - 1, "y": box["y"] + y - 1, "width": 2, "height": 2}))).convert("RGB")
            return im.getpixel((0, 0))
        sel_color, plain = color("die.si"), color("wafer.si")
        assert pg.evaluate("document.querySelector('.s4d').s4dSelect(['wafer.si', '없는부품'])") == ["wafer.si"]
        assert pg.evaluate("window.__ev.length") == 0                                           # 밖에서 넣은 선택은 되알리지 않는다
        assert pg.get_attribute(".key[data-part-id='wafer.si']", "aria-pressed") == "true" and pg.get_attribute(".key[data-part-id='die.si']", "aria-pressed") == "false"
        assert color("die.si") != sel_color                                                     # 강조가 옮겨졌다(선택 해제된 부품의 색이 달라졌다)
        assert color("wafer.si") != plain                                                       # 새로 선택된 부품이 강조됐다
        b.close()
