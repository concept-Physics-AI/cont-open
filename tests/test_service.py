"""서비스 층: 팩 목록과 계산 호출, 실행 ID, 127.0.0.1 제한."""
import http.client
import json
import threading
from dataclasses import asdict

import pytest

from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate
from cont.service import api
from cont.service.serve import make_server


def _inputs():
    steel = 205000.0
    j = BoltedJoint("M10", "10.9", Plate(15.0, steel, 700.0), Plate(15.0, steel, 700.0), outer_diameter=40.0)
    l = LoadCase(50.0, 0.12, 0.12, (0.10, 0.14), axial_load_max=6000.0, transverse_load=1500.0, friction_interface=0.15, embedding=0.008)
    return {"joint": asdict(j), "load": asdict(l)}


@pytest.fixture()
def server():
    srv = make_server(0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown(); srv.server_close()


def _call(port, method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request(method, path, None if body is None else json.dumps(body), {"Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read())


def test_list_packs_names_every_pack_with_limits():
    got = {p["key"]: p for p in api.list_packs()}
    assert {"fastening", "machining", "diagnosis"} <= set(got) and got["fastening"]["limits"]


def test_solve_returns_the_pack_answer_unchanged_with_run_id_and_identity():
    from cont import packs
    from cont.packs.fastening import answer as direct
    r = api.solve("fastening", _inputs())
    ref = packs.get("fastening").solve(_inputs())
    assert r["run_id"].startswith("run-") and r["revision_id"] == ref.revision_id() and r["content_hash"] == ref.content_hash()
    assert r["answer"]["provenance"]["producer"] == "pack:fastening" and r["answer"]["provenance"]["run_id"] == r["run_id"]
    assert r["answer"]["quantities"][0]["value"] == ref.quantities[0].value          # 값은 팩이 낸 그대로
    assert dict(r["trust"])["검증 상태"].startswith("검증 전")
    assert r["revision_id"] in r["truth_line"] and r["run_id"] in r["truth_line"]


def test_same_input_gives_new_run_but_same_revision():
    a, b = api.solve("fastening", _inputs()), api.solve("fastening", _inputs())
    assert a["run_id"] != b["run_id"] and a["revision_id"] == b["revision_id"]


def test_unknown_pack_and_bad_inputs_are_reported_not_hidden():
    with pytest.raises(api.NotFound):
        api.solve("nope", {})
    with pytest.raises(Exception):
        api.solve("fastening", {"joint": {}})


def test_http_endpoints(server):
    st, h = _call(server, "GET", "/v1/health")
    assert st == 200 and h["ok"] is True and {"version", "git_sha", "code_path"} <= set(h["build"])
    st, d = _call(server, "GET", "/v1/packs")
    assert st == 200 and any(p["key"] == "fastening" for p in d["packs"])
    st, d = _call(server, "POST", "/v1/packs/fastening/solve", {"inputs": _inputs(), "question": "체결력은?"})
    assert st == 200 and d["answer"]["question"] == "체결력은?" and d["revision_id"].startswith("rev-")
    st, d = _call(server, "POST", "/v1/packs/nope/solve", {"inputs": {}})
    assert st == 404 and "fastening" in d["available"]
    st, d = _call(server, "POST", "/v1/packs/fastening/solve", {"inputs": {"joint": {}}})
    assert st == 400 and "계산하지 못했습니다" in d["error"]
    assert _call(server, "GET", "/v2/x")[0] == 404


def test_server_refuses_to_open_beyond_this_computer():
    for host in ("0.0.0.0", "192.168.0.5", ""):
        with pytest.raises(ValueError):
            make_server(0, host=host)


def test_body_limit(server):
    c = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    c.request("POST", "/v1/packs/fastening/solve", "{}", {"Content-Length": str(10 ** 8)})
    assert c.getresponse().status == 413


def test_fastening_actions_estimate_and_recommend_through_the_service(server):
    from cont.packs.fastening.estimate import synthetic_elongations
    from cont.dialogue.serve_fastening import example
    j, l = example()
    base = _inputs()
    el = list(synthetic_elongations(j, l, 0.12, 0.0004, 5, seed=1))
    s, est = _call(server, "POST", "/v1/packs/fastening/estimate", {"inputs": {**base, "measured": {"values": el, "instrument_uncertainty": 0.0005, "source": "합성"}}})
    assert s == 200 and est["answer"]["provenance"]["producer"] == "pack:fastening:estimate"
    mu = next(q for q in est["answer"]["quantities"] if q["key"] == "friction_estimated")
    assert abs(mu["value"] - 0.12) < 0.02 and mu["expected_range"][0] < mu["value"] < mu["expected_range"][1]     # 합성 참값 0.12를 범위가 품는다
    assert dict(est["trust"])["검증 상태"].startswith("검증 전")
    s, rec = _call(server, "POST", "/v1/packs/fastening/recommend", {"inputs": {**base, "targets": {"safety_yield": 1.3}}})
    assert s == 200 and rec["answer"]["status"] == "generated"


def test_unknown_action_is_404_and_bad_input_is_400(server):
    assert _call(server, "POST", "/v1/packs/fastening/nope", {"inputs": _inputs()})[0] == 404
    assert _call(server, "POST", "/v1/packs/fastening/recommend", {"inputs": {**_inputs(), "targets": {"bogus": 1}}})[0] == 400


def test_physics_page_is_served_live_and_static_example_is_disabled():
    import re
    from cont.view.physics_page import render_physics
    for live in (True, False):
        page = render_physics(live=live)
        d = json.loads(re.search(r'id="wb-data" type="application/json">(.*?)</script>', page, re.S).group(1))
        assert d["live"] is live and d["estimate"]["answer"]["provenance"]["run_id"].startswith("run-")
        assert "실제 측정 아님" in d["measured_note"]
        assert ("미리 계산한 예시" in page) is True      # 안내 문구는 항상 있고, 로컬에서는 스크립트가 숨긴다


def test_physics_page_route_returns_html(server):
    c = http.client.HTTPConnection("127.0.0.1", server, timeout=20)
    c.request("GET", "/physics"); r = c.getresponse(); body = r.read().decode("utf-8")
    assert r.status == 200 and "체결 작업대" in body and '"live": true' in body
