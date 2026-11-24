"""실행 저장: 종료 후 다시 열어도 같은 입력·모델 버전·결과. 기록은 고치지 않고, 어긋나면 읽지 않는다."""
import http.client
import json
import threading
from dataclasses import asdict

import pytest

from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate
from cont.service import api, runs
from cont.service.serve import make_server


def _inputs():
    steel = 205000.0
    j = BoltedJoint("M10", "10.9", Plate(15.0, steel, 700.0), Plate(15.0, steel, 700.0), outer_diameter=40.0)
    l = LoadCase(50.0, 0.12, 0.12, (0.10, 0.14), axial_load_max=6000.0, transverse_load=1500.0, friction_interface=0.15, embedding=0.008)
    return {"joint": asdict(j), "load": asdict(l)}


@pytest.fixture()
def run_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONT_RUN_DIR", str(tmp_path / "runs"))
    return tmp_path / "runs"


def test_without_store_nothing_is_written_and_run_endpoints_say_so(monkeypatch):
    monkeypatch.delenv("CONT_RUN_DIR", raising=False)
    monkeypatch.setattr(runs, "configured_dir", lambda: None)
    assert api.execute("fastening", _inputs())["stored"] is False
    with pytest.raises(api.NotFound):
        api.list_runs()


def test_run_is_saved_and_reopened_after_restart_with_same_input_model_and_result(run_dir):
    body = api.execute("fastening", _inputs(), "체결력", project_id="p1", asset_id="bolt-1")
    assert body["stored"] is True
    again = runs.RunStore(run_dir)                                  # 프로그램을 다시 연 것과 같다: 새 저장소 객체
    rec = again.get(body["run_id"])
    assert rec["status"] == "complete" and rec["inputs"] == json.loads(json.dumps(_inputs()))
    assert rec["response"]["content_hash"] == body["content_hash"] and rec["response"]["answer"] == body["answer"]
    assert rec["model_version"] == runs.model_version("fastening") and rec["project_id"] == "p1" and rec["asset_id"] == "bolt-1"


def test_recompute_makes_a_new_run_and_keeps_the_old_one(run_dir):
    first = api.execute("fastening", _inputs())
    r = api.recompute(first["run_id"])
    assert r["run"]["run_id"] != first["run_id"] and r["parent_run_id"] == first["run_id"]
    assert r["same_content"] is True and r["model_version_changed"] is False       # 같은 입력이면 내용 해시가 같다
    st = runs.RunStore(run_dir)
    assert st.get(first["run_id"])["parent_run_id"] == "" and st.get(r["run"]["run_id"])["parent_run_id"] == first["run_id"]
    assert len(st.list()) == 2


def test_model_version_change_is_reported(run_dir, monkeypatch):
    first = api.execute("fastening", _inputs())
    monkeypatch.setattr("cont.__version__", "9.9.9")
    assert api.recompute(first["run_id"])["model_version_changed"] is True


def test_failed_run_is_kept_with_reason_and_has_no_result(run_dir):
    with pytest.raises(Exception):
        api.execute("fastening", {"joint": {}, "load": {}})
    [only] = runs.RunStore(run_dir).list()
    rec = runs.RunStore(run_dir).get(only["run_id"])
    assert rec["status"] == "failed" and rec["error"] and rec["response"] is None and rec["content_hash"] == ""


def test_unknown_pack_is_not_recorded(run_dir):
    with pytest.raises(api.NotFound):
        api.execute("nope", {})
    assert runs.RunStore(run_dir).list() == []


def test_records_are_immutable_and_tampering_is_refused(run_dir):
    body = api.execute("fastening", _inputs())
    st = runs.RunStore(run_dir)
    with pytest.raises(FileExistsError):
        st.save(st.get(body["run_id"]))
    p = run_dir / f"{body['run_id']}.json"
    d = json.loads(p.read_text(encoding="utf-8")); d["inputs"]["load"]["target_preload"] = 1
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(runs.RunCorrupt):
        st.get(body["run_id"])
    assert st.list()[0]["status"] == "corrupt"


def test_bad_run_id_is_not_found_and_cannot_escape_the_directory(run_dir):
    st = runs.RunStore(run_dir)
    for bad in ("../x", "run-zzz", "", "run-0123456789ab/../../etc"):
        with pytest.raises(runs.RunNotFound):
            st.get(bad)


def test_http_runs_survive_a_server_restart(run_dir):
    def start():
        srv = make_server(0); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv

    def call(srv, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=20)
        c.request(method, path, None if body is None else json.dumps(body), {"Content-Type": "application/json"})
        r = c.getresponse(); return r.status, json.loads(r.read())

    s1 = start()
    code, body = call(s1, "POST", "/v1/packs/fastening/solve", {"inputs": _inputs(), "project_id": "p1"})
    s1.shutdown(); s1.server_close()
    s2 = start()                                                     # 같은 저장 위치에서 서버를 다시 연다
    try:
        code, got = call(s2, "GET", f"/v1/runs/{body['run_id']}")
        assert code == 200 and got["response"]["content_hash"] == body["content_hash"] and got["project_id"] == "p1"
        code, lst = call(s2, "GET", "/v1/runs?pack=fastening&limit=5")
        assert code == 200 and [r["run_id"] for r in lst["runs"]] == [body["run_id"]]
        code, rc = call(s2, "POST", f"/v1/runs/{body['run_id']}/recompute", {})
        assert code == 200 and rc["same_content"] is True and rc["run"]["run_id"] != body["run_id"]
        assert call(s2, "GET", "/v1/runs/run-000000000000")[0] == 404
    finally:
        s2.shutdown(); s2.server_close()
