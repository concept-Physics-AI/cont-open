import http.client
import json
import re
import shutil
import threading
import time

import pytest

from cont.dialogue.scene_chat import SceneSession
from cont.dialogue.serve_scene import make_server, open_or_new
from cont.generation import get_generator
from cont.llm import LLMResponse
from cont.objspec import ViewState, hybrid_bonding_stack
from cont.service.project import open_project

S = hybrid_bonding_stack()
EDIT = {"steps": [{"id": "a", "tool": "edit_part", "args": {"changes": {"z1": 2.4}}}]}


class Canned:
    name = model = "canned"

    def __init__(self, *replies):
        self.replies = list(replies)

    def complete(self, messages, **opts):
        return LLMResponse(json.dumps(self.replies.pop(0), ensure_ascii=False), "canned", "canned")


class Slow(Canned):
    def __init__(self, gate, *replies):
        super().__init__(*replies)
        self.gate, self.started = gate, threading.Event()

    def complete(self, messages, **opts):
        self.started.set()
        self.gate.wait(5)
        return super().complete(messages, **opts)


def serve(tmp_path, provider=None, **kw):
    ss = SceneSession(S, get_generator("fake"), provider, root=tmp_path / "proj", project_id="p1", name="본딩", **kw)
    srv = make_server(ss, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return ss, srv


def call(srv, method, path, body=None, headers=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Content-Type": "application/json", **(headers or {})} if method == "POST" else dict(headers or {})
    c.request(method, path, raw if raw is not None else (json.dumps(body) if body is not None else None), h)
    r = c.getresponse()
    data = r.read()
    c.close()
    try:
        return r.status, json.loads(data)
    except ValueError:
        return r.status, data.decode("utf-8")


@pytest.fixture
def stop():
    servers = []
    yield servers.append
    for s in servers:
        s.shutdown()
        s.server_close()


def test_state_page_and_scene_are_served_and_scene_carries_the_selection(tmp_path, stop):
    ss, srv = serve(tmp_path, Canned(), selection=("die.si",))
    stop(srv)
    st, state = call(srv, "GET", "/api/state")
    assert st == 200 and state["spec_version"] == S.version and state["state"]["selection"] == ["die.si"] and state["llm"] == "canned"
    st, html = call(srv, "GET", "/scene")
    assert st == 200 and 'data-part-id="die.si" aria-pressed="true"' in html and "s4d:select" in html
    st, page = call(srv, "GET", "/")
    assert st == 200 and 'id="scene"' in page and "/api/select" in page
    assert call(srv, "GET", "/nope")[0] == 404 and call(srv, "POST", "/api/nope", {})[0] == 404


def test_screen_selection_reaches_the_session_and_stale_or_unknown_is_refused_keeping_the_old_one(tmp_path, stop):
    ss, srv = serve(tmp_path, Canned(EDIT))
    stop(srv)
    st, j = call(srv, "POST", "/api/select", {"ids": ["die.si"], "spec_version": S.version})
    assert st == 200 and ss.selection == ("die.si",) and j["state"]["selection"] == ["die.si"]
    st, j = call(srv, "POST", "/api/select", {"ids": ["wafer.si"], "spec_version": "옛버전"})
    assert st == 409 and "오래된 화면" in j["error"] and ss.selection == ("die.si",) and j["state"]["selection"] == ["die.si"]
    st, j = call(srv, "POST", "/api/select", {"ids": ["없는부품"], "spec_version": S.version})
    assert st == 409 and "명세에 없는 부품" in j["error"] and ss.selection == ("die.si",)
    assert call(srv, "POST", "/api/select", {"ids": "die.si", "spec_version": S.version})[0] == 400
    st, j = call(srv, "POST", "/api/turn", {"text": "그 부품 두께를 키워줘"})
    assert st == 200 and j["turn"]["kind"] == "done" and ss.spec.part("die.si").part.z1 == 2.4 and ss.spec.part("wafer.si") == S.part("wafer.si")
    assert j["turns"][-1]["text"] == "그 부품 두께를 키워줘"
    assert call(srv, "POST", "/api/select", {"ids": [], "spec_version": ss.spec.version})[0] == 200 and ss.selection == ()


def test_turn_without_provider_is_refused_and_bad_bodies_are_rejected(tmp_path, stop):
    ss, srv = serve(tmp_path, None)
    stop(srv)
    st, j = call(srv, "POST", "/api/turn", {"text": "카메라를 돌려줘"})
    assert st == 200 and j["turn"]["kind"] == "refused" and "LLM" in j["turn"]["reply"] and j["llm"] is None
    assert call(srv, "POST", "/api/turn", {"text": "  "})[0] == 400
    assert call(srv, "POST", "/api/turn", raw="not json")[0] == 400
    assert call(srv, "POST", "/api/turn", {"text": "x" * 10}, headers={"Content-Type": "text/plain"})[0] == 400          # 다른 사이트의 양식 전송
    assert call(srv, "POST", "/api/turn", {"text": "x"}, headers={"Origin": "http://evil.example"})[0] == 400
    assert call(srv, "POST", "/api/turn", raw="x" * 5000)[0] == 400                                                  # 너무 큰 본문


def test_request_in_progress_blocks_other_writes_with_409(tmp_path, stop):
    gate = threading.Event()
    slow = Slow(gate, EDIT)
    ss, srv = serve(tmp_path, slow)
    stop(srv)
    out = {}
    th = threading.Thread(target=lambda: out.update(r=call(srv, "POST", "/api/turn", {"text": "그 부품 두께를 키워줘"})))
    ss.selection = ("die.si",)
    th.start()
    assert slow.started.wait(5)
    st, j = call(srv, "POST", "/api/select", {"ids": ["wafer.si"], "spec_version": S.version})
    assert st == 409 and "처리하는 중" in j["error"] and ss.selection == ("die.si",)
    gate.set()
    th.join(5)
    assert out["r"][0] == 200 and out["r"][1]["turn"]["kind"] == "done"


def test_save_button_writes_the_project_with_selection_and_conversation_and_reopen_matches(tmp_path, stop):
    ss, srv = serve(tmp_path, Canned(EDIT), playback_t=3.0)
    stop(srv)
    call(srv, "POST", "/api/select", {"ids": ["die.si"], "spec_version": S.version})
    call(srv, "POST", "/api/turn", {"text": "그 부품 두께를 키워줘"})
    st, j = call(srv, "POST", "/api/save", {})
    assert st == 200 and j["turn"]["kind"] == "done" and "저장했습니다" in j["turn"]["reply"] and j["saved_revision"] == 1
    o = open_project(tmp_path / "proj")
    assert o.state.selection == ("die.si",) and o.state.spec.part("die.si").part.z1 == 2.4
    assert [t["text"] for t in o.state.conversation] == ["그 부품 두께를 키워줘", "(저장 단추)"]
    ss2 = open_or_new(tmp_path / "proj", Canned())                                         # 같은 폴더로 다시 열면 이어진다
    ss3, srv3 = ss2, make_server(ss2, 0)
    threading.Thread(target=srv3.serve_forever, daemon=True).start()
    stop(srv3)
    st, j = call(srv3, "GET", "/api/state")
    assert j["state"]["selection"] == ["die.si"] and len(j["turns"]) == 2 and j["saved_revision"] == 1


def test_save_without_project_folder_fails_cleanly_and_discard_with_nothing_pending_is_harmless(tmp_path, stop):
    ss = SceneSession(S, get_generator("fake"), Canned())
    srv = make_server(ss, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    stop(srv)
    st, j = call(srv, "POST", "/api/save", {})
    assert st == 200 and j["turn"]["kind"] == "failed" and "프로젝트 폴더" in j["turn"]["reply"] and j["can_save"] is False
    st, j = call(srv, "POST", "/api/discard", {})
    assert st == 200 and j["turn"] is None


# ---- 실제 Chrome: 화면에서 눌러 고르고, 말하고, 저장한다 -------------------------------------------------------------
def _chrome():
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def _wait(fn, what, sec=8.0):
    end = time.time() + sec
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError(what)


@pytest.mark.skipif(_chrome() is None, reason="Chrome이 없으면 브라우저 점검을 건너뛴다")
def test_real_browser_click_in_the_scene_selects_then_speech_edits_that_part_then_save(tmp_path, stop):
    sync_api = pytest.importorskip("playwright.sync_api")
    view = ViewState().with_camera(azimuth=30.0, elevation=0.0)
    ss, srv = serve(tmp_path, Canned(EDIT), view=view, playback_t=6.0)
    stop(srv)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(executable_path=_chrome(), args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1300, "height": 800})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        fr = lambda: next(f for f in pg.frames if f != pg.main_frame)
        try:
            _wait(lambda: fr().query_selector("canvas[data-ready='1']"), "장면이 그려지지 않았다")
        except AssertionError:
            if "3D 보기를 쓸 수 없습니다" in fr().inner_text(".msg"):
                pytest.skip("이 환경의 브라우저에는 WebGL이 없다")
            raise
        x, y = fr().evaluate("document.querySelector('.s4d').s4dProject('die.si')")
        box = fr().locator("canvas").bounding_box()
        pg.mouse.click(box["x"] + x, box["y"] + y)
        _wait(lambda: ss.selection == ("die.si",), "화면에서 누른 부품이 세션에 들어오지 않았다")
        _wait(lambda: "위 다이" in pg.inner_text("#sel"), "선택 표시가 갱신되지 않았다")
        pg.fill("#t", "그 부품 두께를 키워줘")
        pg.click("#send")
        _wait(lambda: ss.spec.part("die.si").part.z1 == 2.4, "말한 요청이 선택한 부품에 적용되지 않았다")
        _wait(lambda: "z1 2.0→2.4" in pg.inner_text("#log"), "답이 대화창에 보이지 않는다")
        assert ss.spec.part("wafer.si") == S.part("wafer.si")
        _wait(lambda: "v=" in pg.get_attribute("#scene", "src"), "장면이 다시 불러와지지 않았다")
        _wait(lambda: fr().query_selector("canvas[data-ready='1']"), "다시 불러온 장면이 그려지지 않았다")
        assert fr().evaluate("document.querySelector('.s4d').dataset.selected") == "die.si"       # 다시 그려도 선택이 유지된다
        pg.click("#savebtn")
        _wait(lambda: "저장함: 개정 1" in pg.inner_text("#save"), "저장 상태가 보이지 않는다")
        assert open_project(tmp_path / "proj").state.selection == ("die.si",)
        pg.mouse.click(box["x"] + 6, box["y"] + 6)                                                 # 빈 곳: 선택 해제도 세션에 들어간다
        _wait(lambda: ss.selection == (), "선택 해제가 세션에 들어오지 않았다")
        b.close()
    assert errors == []
