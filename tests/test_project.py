import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import cont.generation.providers as providers
from cont.generation import get_generator
from cont.objspec import ViewState, edit_selection, generate_image, hybrid_bonding_stack, select
from cont.service import project as P
from cont.service.project import ProjectError, open_project, restore_version, save_project

S = hybrid_bonding_stack()
VIEW = ViewState().with_camera(azimuth=100.0, elevation=30.0).with_speed(S, 2, 0.5)


def _img(spec=S, stage="contact"):
    return generate_image(spec, get_generator("fake"), stage, rep_id="image")


def _save(root, spec=S, **kw):
    kw.setdefault("view", VIEW)
    kw.setdefault("selection", ("die.si",))
    kw.setdefault("playback_t", 3.2)
    kw.setdefault("images", [_img(spec)])
    return save_project(root, "p1", "본딩 설명", spec, **kw)


def test_round_trip_restores_everything_without_calling_a_model(tmp_path, monkeypatch):
    img = _img()
    _save(tmp_path, images=[img])
    monkeypatch.setattr(providers.Fake, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("모델을 다시 불렀다")))
    o = open_project(tmp_path)
    st = o.state
    assert st.spec == S and st.spec.version == S.version
    assert st.view == VIEW and st.selection == ("die.si",) and st.playback_t == 3.2
    assert len(st.images) == 1 and st.images[0].status == "ok"
    assert st.images[0].png == img.result.png and st.images[0].record["sha256"] == img.result.sha256
    assert st.images[0].record["object_spec"]["spec_version"] == S.version
    assert o.problems == [] and not o.recovered_from_previous and o.revision == 1


def test_reopen_in_a_new_process_gives_the_same_state(tmp_path):
    img = _img()
    _save(tmp_path, images=[img])
    code = ("import json,sys;from cont.service.project import open_project;o=open_project(sys.argv[1]);s=o.state;"
            "print(json.dumps([s.spec.version,s.view.to_dict(),list(s.selection),s.playback_t,[__import__('hashlib').sha256(i.png).hexdigest() for i in s.images]]))")
    r = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(Path(P.__file__).parents[2])})
    assert r.returncode == 0, r.stderr
    ver, view, sel, t, shas = json.loads(r.stdout)
    assert ver == S.version and view == VIEW.to_dict() and sel == ["die.si"] and t == 3.2 and shas == [img.result.sha256]


def test_edited_spec_adds_a_version_with_parent_and_old_one_can_be_restored(tmp_path):
    _save(tmp_path)
    new = edit_selection(S, select(S, "die.si"), z1=2.4).new
    _save(tmp_path, spec=new, images=[_img(new)])
    o = open_project(tmp_path)
    assert o.state.spec == new and o.revision == 2 and len(o.history) == 2
    assert o.history[1]["parent_art"] == o.history[0]["art"] and o.history[1]["parent_version"] == S.version
    assert o.state.spec.parent_version == S.version
    assert len(o.state.images) == 2
    old = restore_version(tmp_path, S.version)
    assert old.version == S.version and open_project(tmp_path).state.spec == new          # 현재는 바뀌지 않는다
    with pytest.raises(ProjectError):
        restore_version(tmp_path, "0" * 64)


def test_saving_same_state_again_does_not_duplicate(tmp_path):
    img = _img()
    _save(tmp_path, images=[img])
    _save(tmp_path, images=[img])
    o = open_project(tmp_path)
    assert o.revision == 2 and len(o.history) == 1 and len(o.state.images) == 1
    assert len(list((tmp_path / "files").glob("*.png"))) == 1


def test_two_projects_with_same_part_names_do_not_mix(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    save_project(a, "pa", "A", S, images=[_img()])
    save_project(b, "pb", "B", S, images=[_img()])
    oa, ob = open_project(a), open_project(b)
    assert oa.project_id == "pa" and ob.project_id == "pb"
    assert {h["art"] for h in oa.history}.isdisjoint({h["art"] for h in ob.history})       # 같은 명세라도 프로젝트가 다르면 다른 항목
    with pytest.raises(ProjectError):
        save_project(a, "pb", "B", S)                                                       # 다른 프로젝트 폴더에 저장 거절


def test_foreign_manifest_is_refused(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    save_project(a, "pa", "A", S)
    save_project(b, "pb", "B", S)
    (b / P.MANIFEST).write_bytes((a / P.MANIFEST).read_bytes())          # pa의 manifest를 pb 폴더에 넣음
    (b / P.PREV).unlink(missing_ok=True)
    with pytest.raises(ProjectError):
        open_project(b)


def test_missing_image_opens_with_problem_but_missing_spec_does_not(tmp_path):
    _save(tmp_path)
    png = next((tmp_path / "files").glob("*.png"))
    png.unlink()
    o = open_project(tmp_path)
    assert o.state.images[0].status == "missing" and o.state.images[0].png is None and any("없습니다" in p for p in o.problems)
    next((tmp_path / "files").glob("*.spec.json")).unlink()
    with pytest.raises(ProjectError, match="명세 파일이 없습니다"):
        open_project(tmp_path)


def test_tampered_files_are_detected(tmp_path):
    _save(tmp_path)
    png = next((tmp_path / "files").glob("*.png"))
    png.write_bytes(png.read_bytes() + b"x")
    o = open_project(tmp_path)
    assert o.state.images[0].status == "changed" and o.state.images[0].png is None and o.problems
    spec_file = next((tmp_path / "files").glob("*.spec.json"))
    spec_file.write_text(spec_file.read_text(encoding="utf-8").replace("20.0", "21.0", 1), encoding="utf-8")
    with pytest.raises(ProjectError, match="명세를 열 수 없습니다"):
        open_project(tmp_path)


def test_corrupt_manifest_falls_back_to_previous_good_one(tmp_path):
    _save(tmp_path)
    _save(tmp_path, selection=("wafer.si",), playback_t=1.0)
    m = tmp_path / P.MANIFEST
    m.write_text(m.read_text(encoding="utf-8")[:40], encoding="utf-8")                      # 잘림
    o = open_project(tmp_path)
    assert o.recovered_from_previous and o.state.selection == ("die.si",) and o.revision == 1 and o.problems
    (tmp_path / P.PREV).write_text("{", encoding="utf-8")
    with pytest.raises(ProjectError):
        open_project(tmp_path)


def test_hand_edited_manifest_is_not_trusted(tmp_path):
    _save(tmp_path)
    _save(tmp_path)
    m = tmp_path / P.MANIFEST
    raw = json.loads(m.read_text(encoding="utf-8"))
    raw["body"]["playback_t"] = 99.0                                                        # 해시를 그대로 두고 값만 고침
    m.write_text(json.dumps(raw), encoding="utf-8")
    o = open_project(tmp_path)
    assert o.recovered_from_previous and o.state.playback_t == 3.2


def test_unsupported_schema_is_refused_not_guessed(tmp_path):
    _save(tmp_path)
    m = tmp_path / P.MANIFEST
    raw = json.loads(m.read_text(encoding="utf-8"))
    raw["body"]["schema_version"] = 2
    raw["body_sha256"] = P.sha256_bytes(P._canon(raw["body"]))
    m.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProjectError, match="지원하지 않는 저장 형식"):
        open_project(tmp_path)


def test_nothing_saved_yet(tmp_path):
    with pytest.raises(ProjectError, match="저장된 프로젝트가 없습니다"):
        open_project(tmp_path / "nope")


def test_bad_inputs_are_refused_before_writing(tmp_path):
    new = edit_selection(S, select(S, "die.si"), z1=2.4).new
    with pytest.raises(ProjectError, match="저장되지 않은 명세"):
        save_project(tmp_path, "p1", "x", S, images=[_img(new)])
    with pytest.raises(ProjectError, match="명세에 없는 부품"):
        save_project(tmp_path, "p1", "x", S, selection=("nope",))
    for t in (-1, 99, True, "3"):
        with pytest.raises(ProjectError, match="재생 위치"):
            save_project(tmp_path, "p1", "x", S, playback_t=t)
    with pytest.raises(ProjectError):
        save_project(tmp_path, "", "x", S)
    assert not (tmp_path / P.MANIFEST).exists()


def test_crash_while_replacing_manifest_keeps_last_good_save(tmp_path, monkeypatch):
    _save(tmp_path)
    real = os.replace

    def boom(src, dst, *a, **k):
        if str(dst).endswith(P.MANIFEST):
            raise OSError("종료")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(P.os, "replace", boom)
    with pytest.raises(OSError):
        _save(tmp_path, selection=("wafer.si",), playback_t=1.0)
    monkeypatch.setattr(P.os, "replace", real)
    o = open_project(tmp_path)
    assert o.state.selection == ("die.si",) and o.state.playback_t == 3.2 and not o.recovered_from_previous
    assert not list(tmp_path.glob("*.tmp")) and not (tmp_path / P.LOCK).exists()


def test_concurrent_save_is_refused_and_stale_lock_is_cleared(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / P.LOCK).write_text("1")
    with pytest.raises(ProjectError, match="진행 중"):
        _save(tmp_path)
    old = time.time() - 3600
    os.utime(tmp_path / P.LOCK, (old, old))
    _save(tmp_path)
    assert open_project(tmp_path).revision == 1 and not (tmp_path / P.LOCK).exists()


# ---- 대화 기록 -----------------------------------------------------------------------------------------------------
def _turn(i, kind="done", text=None):
    return {"text": text or f"요청 {i}", "kind": kind, "reply": f"답 {i}",
            "steps": [{"id": "s1", "tool": "set_camera", "state": "done", "error": ""}], "changes": [f"변경 {i}"], "request_id": f"r{i}"}


def test_conversation_round_trips_and_is_kept_when_not_passed_again(tmp_path):
    conv = [_turn(1), _turn(2, "refused")]
    _save(tmp_path, conversation=conv)
    o = open_project(tmp_path)
    assert o.state.conversation == conv and not o.problems
    _save(tmp_path, spec=S, playback_t=1.0)                   # conversation을 주지 않으면 이전 기록을 그대로 둔다
    assert open_project(tmp_path).state.conversation == conv
    _save(tmp_path, playback_t=1.0, conversation=[])          # 빈 목록은 비우는 것이다
    assert open_project(tmp_path).state.conversation == []


def test_save_conversation_only_updates_conversation_not_revision_or_state(tmp_path):
    r = _save(tmp_path)
    before = open_project(tmp_path)
    out = P.save_conversation(tmp_path, "p1", [_turn(1)])
    after = open_project(tmp_path)
    assert out["revision"] == r["revision"] == after.revision == before.revision
    assert after.state.spec == before.state.spec and after.state.view == before.state.view and after.state.selection == before.state.selection
    assert after.state.conversation == [_turn(1)]
    with pytest.raises(ProjectError, match="다른 프로젝트"):
        P.save_conversation(tmp_path, "other", [])


def test_old_manifest_without_conversation_opens_with_empty_history(tmp_path):
    _save(tmp_path)
    mp = tmp_path / "manifest.json"
    raw = json.loads(mp.read_text(encoding="utf-8"))
    del raw["body"]["conversation"]
    raw["body_sha256"] = P.sha256_bytes(P._canon(raw["body"]))
    mp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    o = open_project(tmp_path)
    assert o.state.conversation == [] and not o.problems


def test_conversation_is_trimmed_and_long_text_is_cut_with_a_mark(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    (cfg / "objspec").mkdir(parents=True)
    (cfg / "objspec" / "project.yaml").write_text("lock_stale_seconds: 60\nconversation_max_turns: 3\nconversation_text_max_chars: 10\n", encoding="utf-8")
    out = P._clean_conversation([_turn(i, text="가" * 30) for i in range(5)], cfg)
    assert [t["request_id"] for t in out] == ["r2", "r3", "r4"]                  # 최근 3턴만
    assert out[0]["text"] == "가" * 10 + "…(잘림)"


@pytest.mark.parametrize("bad", [[{"kind": "weird"}], ["문자열"], [{**_turn(1), "steps": [{"tool": 3, "state": "done"}]}], [{**_turn(1), "text": 5}]])
def test_bad_conversation_is_refused_at_save(tmp_path, bad):
    with pytest.raises(ProjectError):
        _save(tmp_path, conversation=bad)


def test_tampered_conversation_is_caught_by_the_hash_and_previous_save_is_used(tmp_path):
    _save(tmp_path, conversation=[_turn(1)])
    _save(tmp_path, playback_t=1.0, conversation=[_turn(1), _turn(2)])
    mp = tmp_path / "manifest.json"
    raw = json.loads(mp.read_text(encoding="utf-8"))
    raw["body"]["conversation"][0]["reply"] = "손으로 고침"
    mp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    o = open_project(tmp_path)
    assert o.recovered_from_previous and o.state.conversation == [_turn(1)]
