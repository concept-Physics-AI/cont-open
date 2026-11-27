"""장면 대화 화면을 내 PC에서 띄우는 작은 서버 (표준 라이브러리만 사용, 127.0.0.1에서만 받는다).

한 화면에 3D 장면(부품 클릭 선택), 대화, 저장을 둔다. 화면에서 고른 부품은 `SceneSession.select_from_screen`으로 세션에 들어가
다음 말의 "그 부품"이 된다. 요청 처리·되돌리기·저장은 모두 `SceneSession`이 하며 이 서버는 전달만 한다.

새 프로젝트로 시작:  python -m cont.dialogue.serve_scene --root <폴더> --llm
저장한 프로젝트 열기: 같은 명령 (폴더에 저장된 프로젝트가 있으면 연다)
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cont.dialogue.scene_chat import SceneSession
from cont.generation import get_generator
from cont.objspec import ObjectSpecError, SelectionError, hybrid_bonding_stack
from cont.view.scene4d import scene4d_page

MAX_BODY = 4000
LOG_TURNS = 60                   # 화면에 보내는 최근 대화 수


class SceneApp:
    """세션 하나와 그 잠금. 요청 처리 중에는 다른 쓰기를 받지 않는다(409)."""

    def __init__(self, session: SceneSession):
        self.session, self.lock, self.version = session, threading.Lock(), 0

    def snapshot(self) -> dict[str, Any]:
        s = self.session
        return {"version": self.version, "spec_version": s.spec.version, "state": s.state_json(), "turns": [t.to_dict() for t in s.turns[-LOG_TURNS:]],
                "pending": s.pending(), "problems": list(s.open_problems), "saved_revision": s.saved_revision, "can_save": s.root is not None,
                "llm": getattr(s.provider, "name", None)}

    def scene_html(self) -> str:
        s = self.session
        return scene4d_page(s.spec, s.view, start_t=min(max(s.playback_t, 0.0), s.duration()), selection=s.selection)


def _page(title: str) -> str:
    return PAGE.replace("__TITLE__", title)


def make_handler(app: SceneApp, title: str = "장면 대화"):
    page = _page(title).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if path not in ("/scene", "/api/state"):
                return self._send(404, b"not found", "text/plain")
            with app.lock:                                   # 요청 처리 중에는 끝난 뒤의 상태를 준다
                if path == "/scene":
                    return self._send(200, app.scene_html().encode("utf-8"), "text/html; charset=utf-8")
                return self._json(200, app.snapshot())

        def _body(self) -> dict[str, Any] | None:
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return None                                  # 다른 사이트의 양식 전송을 거른다(JSON은 사전 확인 없이는 보낼 수 없다)
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return None
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 <= n <= MAX_BODY:
                    return None
                d = json.loads(self.rfile.read(n) or b"{}")
                return d if isinstance(d, dict) else None
            except (ValueError, UnicodeDecodeError):
                return None

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path not in ("/api/turn", "/api/select", "/api/resume", "/api/discard", "/api/save"):
                return self._send(404, b"not found", "text/plain")
            d = self._body()
            if d is None:
                return self._json(400, {"error": "요청 형식이 맞지 않습니다"})
            if not app.lock.acquire(blocking=False):
                return self._json(409, {"error": "이전 요청을 처리하는 중입니다. 끝난 뒤 다시 하세요"})
            try:
                s = app.session
                if path == "/api/select":
                    ids, ver = d.get("ids"), d.get("spec_version")
                    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or not isinstance(ver, str):
                        return self._json(400, {"error": "ids(목록)와 spec_version(문자열)이 필요합니다"})
                    try:
                        s.select_from_screen(ids, ver)
                    except (SelectionError, ObjectSpecError) as e:
                        return self._json(409, {"error": str(e), **app.snapshot()})
                    app.version += 1
                    return self._json(200, {"ok": True, **app.snapshot()})
                if path == "/api/turn":
                    text = d.get("text")
                    if not isinstance(text, str) or not text.strip():
                        return self._json(400, {"error": "말을 입력하세요"})
                    t = s.turn(text.strip()[:600])
                elif path == "/api/resume":
                    t = s.resume_pending()
                elif path == "/api/save":
                    t = s.save_now()
                else:
                    t = None
                    s.discard_pending()
                app.version += 1
                return self._json(200, {"turn": t.to_dict() if t else None, **app.snapshot()})
            finally:
                app.lock.release()

        def log_message(self, *_: Any) -> None:
            pass

    return Handler


def make_server(session: SceneSession, port: int = 8770, title: str = "장면 대화") -> ThreadingHTTPServer:
    app = SceneApp(session)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, title))
    srv.scene_app = app  # type: ignore[attr-defined]
    return srv


def open_or_new(root: str | Path, provider: Any | None = None, generator_name: str = "fake") -> SceneSession:
    root = Path(root)
    gen = get_generator(generator_name)
    if (root / "manifest.json").exists():
        return SceneSession.open(root, gen, provider)
    return SceneSession(hybrid_bonding_stack(), gen, provider, root=root, project_id="scene-1", name="본딩 장면")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="프로젝트 폴더(저장·다시 열기). 저장소 밖에 두세요")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--llm", nargs="?", const="", default=None, metavar="공급자", help="말을 계획으로 푸는 LLM (이름을 비우면 기본 공급자)")
    ap.add_argument("--generator", default="fake", help="이미지 생성기 이름(기본: fake — 가짜 그림이며 화면에도 그렇게 표시된다)")
    a = ap.parse_args(argv)
    provider = None
    if a.llm is not None:
        from cont.llm import get_provider
        provider = get_provider(a.llm or None)
    session = open_or_new(a.root, provider, a.generator)
    srv = make_server(session, a.port)
    print(f"http://127.0.0.1:{a.port}  (끝내기: Ctrl+C)  LLM: {getattr(provider, 'name', '연결 안 됨 — 말은 거절됩니다')}  폴더: {a.root}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
:root{--bg:#F5F7FA;--panel:#fff;--ink:#18385E;--sub:#5B6B7F;--line:#C9D3E0;--sig:#008E94;--hi:#D6336C;--bad:#B3261E}
@media(prefers-color-scheme:dark){:root{--bg:#10151C;--panel:#171E27;--ink:#E6ECF4;--sub:#9AA9BC;--line:#2B3644;--sig:#38B6BC;--hi:#FF7AA2;--bad:#FF8A80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{display:grid;grid-template-columns:minmax(320px,1.15fr) minmax(300px,1fr);gap:14px;padding:14px;min-height:100vh}
@media(max-width:820px){main{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}
iframe{width:100%;height:720px;border:0;display:block;background:var(--bg)}
.scenecard{align-self:start}
.side{display:flex;flex-direction:column;gap:10px;min-height:0}
.bar{padding:10px 12px;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;font-size:14px}
.bar b{font-weight:600}.sub{color:var(--sub)}
#log{padding:10px 12px;overflow:auto;max-height:46vh;display:flex;flex-direction:column;gap:10px}
.m{white-space:pre-wrap;word-break:break-word}.u{font-weight:600}.r{padding-left:10px;border-left:3px solid var(--line)}
.r.failed,.r.refused{border-left-color:var(--bad)}.r.done{border-left-color:var(--sig)}
form{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--line)}
input[type=text]{flex:1;min-width:0;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
button{font:inherit;padding:7px 12px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);cursor:pointer}
button.go{background:var(--sig);color:#fff;border-color:var(--sig)}button:disabled{opacity:.55;cursor:default}
:focus-visible{outline:2px solid var(--hi);outline-offset:2px}
#warn{padding:10px 12px;color:var(--bad);display:none;white-space:pre-wrap}#warn.on{display:block}
#pend{padding:10px 12px;display:none;gap:8px;flex-wrap:wrap;align-items:center;border-left:3px solid var(--hi)}#pend.on{display:flex}
</style></head><body><main>
<section class="card scenecard" aria-label="3D 장면"><iframe id="scene" title="3D 장면: 부품을 누르면 선택됩니다" src="/scene"></iframe></section>
<section class="side">
 <div class="card"><div class="bar"><span>선택: <b id="sel">없음</b></span><span class="sub" id="save"></span><button id="savebtn" type="button">저장</button></div>
 <div id="warn" role="alert"></div>
 <div id="pend"><span id="pendtxt"></span><button id="resume" type="button">이어서 실행</button><button id="discard" type="button">버리기</button></div></div>
 <div class="card" style="display:flex;flex-direction:column;min-height:0;flex:1">
  <div id="log" aria-live="polite"><span class="sub">장면의 부품을 누르고 "그 부품 두께를 키워줘"처럼 말해 보세요. 요청 하나가 실패하면 그 요청의 변경은 모두 되돌려집니다.</span></div>
  <form id="f"><input id="t" type="text" autocomplete="off" aria-label="말하기" placeholder="무엇을 할까요?" maxlength="600"><button class="go" id="send">보내기</button></form>
 </div>
</section></main>
<script>
var $=function(i){return document.getElementById(i)},rev=-1,names={},busy=false;
function api(path,body){return fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})
 .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}},function(){return {ok:false,j:{error:'응답을 읽지 못했습니다'}}})},function(){return {ok:false,j:{error:'서버에 연결하지 못했습니다'}}})}
function add(cls,text){var d=document.createElement('div');d.className=cls;d.textContent=text;$('log').appendChild(d);return d}
function warn(t){$('warn').textContent=t||'';$('warn').className=t?'on':''}
function paint(j){
 names={};(j.state.parts||[]).forEach(function(p){names[p.id]=p.name});
 $('sel').textContent=j.state.selection.length?j.state.selection.map(function(i){return names[i]||i}).join(', '):'없음';
 $('save').textContent=j.can_save?(j.saved_revision?('저장함: 개정 '+j.saved_revision):'아직 저장 안 함')+(j.state.unsaved_images?(' · 저장 전 이미지 '+j.state.unsaved_images+'개'):''):'저장 폴더 없음';
 $('savebtn').disabled=!j.can_save||busy;
 var p=j.pending;$('pend').className=p?'on':'';
 if(p){$('pendtxt').textContent='중단된 요청: '+p.text+(p.stale?' (이어 갈 수 없음: '+p.stale+')':'');$('resume').disabled=!!p.stale||busy}
 var w=(j.problems||[]).slice();if(!j.llm)w.push('LLM이 연결되어 있지 않아 말은 거절됩니다. 부품 선택과 저장은 됩니다.');warn(w.join('\\n'));
 rev=j.version}
function fill(j){$('log').textContent='';if(!j.turns.length)add('sub','장면의 부품을 누르고 "그 부품 두께를 키워줘"처럼 말해 보세요. 요청 하나가 실패하면 그 요청의 변경은 모두 되돌려집니다.');
 j.turns.forEach(function(t){add('m u',t.text);add('m r '+t.kind,t.reply)});$('log').scrollTop=1e9}
function reloadScene(j){$('scene').src='/scene?v='+j.version}
function hook(){var d=$('scene').contentDocument,b=d&&d.querySelector('.s4d');if(!b)return;
 b.addEventListener('s4d:select',function(e){api('/api/select',{ids:e.detail.ids,spec_version:e.detail.spec_version}).then(function(r){
  if(r.ok){paint(r.j);warn(r.j.problems&&r.j.problems.length?r.j.problems.join('\\n'):'')}
  else{warn(r.j.error||'선택하지 못했습니다');if(r.j.version!==undefined){paint(r.j);warn(r.j.error);reloadScene(r.j)}}})})}
$('scene').addEventListener('load',hook);
function act(path,body){if(busy)return;busy=true;$('send').disabled=true;$('savebtn').disabled=true;
 return api(path,body).then(function(r){busy=false;$('send').disabled=false;
  if(!r.ok&&r.j.version===undefined){warn(r.j.error||'실패했습니다');$('savebtn').disabled=false;return}
  fill(r.j);paint(r.j);reloadScene(r.j)})}
$('f').addEventListener('submit',function(e){e.preventDefault();var v=$('t').value.trim();if(!v)return;$('t').value='';add('m u',v);add('m r','처리 중…');act('/api/turn',{text:v})});
$('savebtn').addEventListener('click',function(){act('/api/save',{})});
$('resume').addEventListener('click',function(){act('/api/resume',{})});
$('discard').addEventListener('click',function(){act('/api/discard',{})});
api('/api/state').then(function(r){if(r.ok){fill(r.j);paint(r.j)}else warn(r.j.error||'상태를 읽지 못했습니다')});
</script></body></html>"""


if __name__ == "__main__":
    main()
