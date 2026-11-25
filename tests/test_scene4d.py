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
