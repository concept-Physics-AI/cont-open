"""체결 화면과 대화로 바꾸기를 내 PC에서 띄우는 작은 서버 (표준 라이브러리만 사용, 127.0.0.1에서만 받는다).

기본 예제로:        python -m cont.dialogue.serve_fastening
LLM으로 말 읽기:    python -m cont.dialogue.serve_fastening --llm            (config/llm의 기본 공급자)
"""
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from functools import lru_cache
from typing import Any

import yaml

from cont.dialogue.fastening_chat import Session, Turn, brief
from cont.dialogue.fastening_talk import screen_intent, suggest, talk
from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate
from cont.view import render_fastening
from cont.tolerance import CONFIG_DIR
from cont.view.fastening_app import IDEAS, render_app
from cont.view.fastening_live import render_live, state

MAX_BODY = 4000
TREE_STATES = 10         # 공개 시연에 미리 계산해 싣는 설계 상태의 수 (파일 크기를 정한다)


def example() -> tuple[BoltedJoint, LoadCase]:
    """시연용 출발 조인트: M10 10.9, 강판 15 mm 두 장."""
    steel = 205000.0
    return (BoltedJoint("M10", "10.9", Plate(15.0, steel, 700.0), Plate(15.0, steel, 700.0), outer_diameter=40.0),
            LoadCase(50.0, 0.12, 0.12, (0.10, 0.14), axial_load_max=6000.0, transverse_load=1500.0, friction_interface=0.15, embedding=0.008))


def source_text(t: Turn) -> str:
    base = "말을 읽은 방법: LLM" if t.source == "llm" else "말을 읽은 방법: 규칙 (LLM 없음)"
    return base + (f" · {t.note}" if t.note else "")


def page(session: Session, ask_url: str | None, subtitle: str = "") -> str:
    before = session.turns[-1].before if session.turns and session.turns[-1].changes else None
    downloads = (("STEP", "/joint.step"), ("STL", "/joint.stl")) if ask_url else ()
    return render_fastening(session.joint, session.load, session.answer, before,
                            [(t.text, t.reply, source_text(t)) for t in session.turns], ask_url, subtitle=subtitle, downloads=downloads)


def live_state(session: Session, turn: Turn | None = None) -> dict[str, Any]:
    """움직이는 화면이 그리는 지금 상태. turn을 주면 그 말에 대한 짧은 답과 자세한 글이 붙는다."""
    before = turn.before if turn and turn.changes else None
    return state(session.joint, session.load, session.answer, before, brief(turn) if turn else None,
                 (turn.reply + "\n\n" + source_text(turn)) if turn else "")


def live_page(session: Session, ask_url: str | None) -> str:
    return render_live([live_state(session)], ask_url, downloads=(("STEP", "/joint.step"), ("STL", "/joint.stl")) if ask_url else ())


def scripted(texts: tuple[str, ...], provider: Any | None = None) -> list[dict[str, Any]]:
    """예제 조인트에서 시작해 말을 차례로 한 상태들 (파일로 내는 시연용)."""
    session = Session(*example(), provider=provider)
    states = [live_state(session)]
    for text in texts:
        states.append(live_state(session, session.say(text)))
    return states


@lru_cache(maxsize=1)
def links() -> dict[str, str]:
    with open(CONFIG_DIR / "fastening" / "default.yaml", encoding="utf-8") as f:
        a = (yaml.safe_load(f) or {})["app"]
    return {"모형 설명": a["model_doc_url"], "코드": a["repo_url"]}


def message(session: Session, text: str) -> dict[str, Any]:
    """대화 화면에 보내는 한 번의 답: 지금 상태, 풀어 쓴 답, 바뀐 값, 화면에서 열 곳, 다음에 할 만한 말."""
    intent = screen_intent(text, session)
    if intent:
        return {"state": None, "talk": intent["talk"], "brief": None,
                "ui": {"view": intent["view"], "open": intent["open"]}, "detail": "", "suggest": suggest(session, text)}
    t = session.say(text)
    return {"state": state(session.joint, session.load, session.answer, t.before if t.changes else None), "talk": talk(t), "brief": brief(t),
            "ui": None, "detail": t.reply + "\n\n" + source_text(t), "suggest": suggest(session, text)}


def app_page(session: Session, ask_url: str | None = "/ask") -> str:
    data = {"states": {"s0": state(session.joint, session.load, session.answer)},
            "nodes": {"start": {"sid": "s0", "next": {}, "suggest": suggest(session)}}, "start": "start"}
    return render_app(data, ask_url, links=links(), downloads=(("STEP", "/joint.step"), ("STL", "/joint.stl")))


def tree(max_states: int = TREE_STATES) -> dict[str, Any]:
    """공개 시연용: 추천 문구를 따라갈 수 있는 대화를 미리 계산한다 (서버 없이 파일 하나로 돈다).

    마디 하나 = 어떤 화면 상태에서 어떤 말을 했는가. 같은 마디는 하나로 합친다.
    설계 상태가 max_states개를 넘으면 그 너머로 가는 문구는 싣지 않는다.
    """
    def design(s: Session) -> str:
        return json.dumps([asdict(s.joint), asdict(s.load), [asdict(c.joint) | {"torque": c.torque} for c in s.offers]],
                          ensure_ascii=False, sort_keys=True, default=str)

    root = Session(*example())
    states: dict[str, Any] = {"s0": state(root.joint, root.load, root.answer)}
    nodes: dict[str, Any] = {"start": {"sid": "s0", "next": {}}}
    seen: dict[tuple[str, str, str], str] = {}
    designs = {design(root)}
    queue: list[tuple[str, Session, list[str]]] = [("start", root, [t for t, _ in IDEAS])]
    while queue:
        nid, at, offers = queue.pop(0)
        for text in offers:
            s = copy.deepcopy(at)
            m = message(s, text)
            d = design(s)
            if d not in designs and len(designs) >= max_states:
                continue
            designs.add(d)
            key = (d, text, nodes[nid]["sid"] if m["state"] is None else "")
            if key not in seen:
                seen[key] = f"n{len(seen) + 1}"
                if m["state"] is None:                   # 화면만 바꾸는 말: 그림은 그대로다
                    sid = nodes[nid]["sid"]
                else:
                    sid = f"s{len(states)}"
                    states[sid] = m["state"]
                nodes[seen[key]] = {"sid": sid, "talk": m["talk"], "brief": m["brief"], "ui": m["ui"], "detail": m["detail"], "next": {}}
                queue.append((seen[key], s, m["suggest"]))
            nodes[nid]["next"][text] = seen[key]
    return {"states": states, "nodes": nodes, "start": "start"}


def make_server(session: Session, port: int = 8766, subtitle: str = "") -> ThreadingHTTPServer:
    box = {"s": session}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def _download(self, kind: str) -> None:
            """지금 조인트의 형상을 파일로 내려 준다."""
            import os
            import tempfile

            from cont.packs.fastening.export import export_step, export_stl
            fd, tmp = tempfile.mkstemp(suffix="." + kind); os.close(fd)
            try:
                (export_step if kind == "step" else export_stl)(box["s"].joint, tmp)
                with open(tmp, "rb") as f:
                    body = f.read()
            finally:
                os.unlink(tmp)
            self.send_response(200); self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{box["s"].joint.size}_joint.{kind}"')
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            session = box["s"]
            if self.path in ("/", "/index.html"):
                self._send(200, app_page(session).encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/live":
                self._send(200, live_page(session, "/say").encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/classic":
                self._send(200, page(session, None, subtitle).encode("utf-8"), "text/html; charset=utf-8")
            elif self.path in ("/joint.stl", "/joint.step"):
                self._download(self.path.rsplit(".", 1)[1])
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/reset":            # 새 설계: 예제 조인트로 돌아간다 (말 읽는 방법은 그대로)
                box["s"] = Session(*example(), provider=box["s"].provider)
                return self._send(200, b"{}", "application/json")
            if self.path not in ("/say", "/ask"):
                return self._send(404, b"not found", "text/plain")
            session = box["s"]
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= MAX_BODY:
                    raise ValueError("bad length")
                text = str(json.loads(self.rfile.read(n)).get("text", "")).strip()
                if not text:
                    raise ValueError("empty")
            except (ValueError, json.JSONDecodeError, AttributeError):
                return self._send(400, json.dumps({"reply": "말을 읽지 못했습니다."}, ensure_ascii=False).encode(), "application/json")
            if self.path == "/ask":              # 대화 화면
                return self._send(200, json.dumps(message(session, text), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            t = session.say(text)
            body = {**live_state(session, t), "reply": t.reply, "changes": t.changes, "source": source_text(t)}
            self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, *_: Any) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--llm", nargs="?", const="", default=None, metavar="공급자")
    ap.add_argument("--classic", action="store_true", help="--out과 함께: 움직이는 화면 대신 예전의 긴 문서형 화면으로 쓴다")
    ap.add_argument("--live", action="store_true", help="--out과 함께: 대화 화면 대신 예전의 한 화면(차례로 넘기는 시연)으로 쓴다")
    ap.add_argument("--out", help="서버를 띄우지 않고, 예시 대화를 실행한 화면을 파일로 쓴다")
    a = ap.parse_args(argv)
    provider = None
    if a.llm is not None:
        from cont.llm import get_provider
        provider = get_provider(a.llm or None)
    session = Session(*example(), provider=provider)
    if a.out:
        texts = ("토크 75로 올려줘", "M12로 바꾸고 머리 쪽 판 두께 20", "축방향 하중 12 kN", "항복 안전율 1.5 이상, 미끄럼 안전율 2.5 이상이 되게 해 줘", "1번으로")
        if a.classic:
            for text in texts:
                session.say(text)
            content = page(session, None, "시연: M10 10.9 조인트에서 시작해 대화로 바꾼 결과")
        elif a.live:
            content = render_live(scripted(texts, provider))
        else:
            data = tree()
            content = render_app(data, None, links=links())
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"written {a.out}: {len(data['nodes'])} nodes, {len(data['states'])} states (app)")
            return
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"written {a.out}: {len(texts)} turns ({'classic' if a.classic else 'live'})")
        return
    srv = make_server(session, a.port, "대화로 값을 바꾸면 다시 계산합니다")
    print(f"http://127.0.0.1:{a.port}  (끝내기: Ctrl+C)  LLM: {getattr(provider, 'name', '쓰지 않음')}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
