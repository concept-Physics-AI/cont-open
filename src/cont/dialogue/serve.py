"""진단 화면과 묻고 답하기를 내 PC에서 띄우는 작은 서버 (표준 라이브러리만 사용, 127.0.0.1에서만 받는다).

가상 설비로:        python -m cont.dialogue.serve
현장 설정 파일로:   python -m cont.dialogue.serve --site site.yaml
LLM으로 말 다듬기:  python -m cont.dialogue.serve --llm            (config/llm의 기본 공급자)
                    python -m cont.dialogue.serve --llm ollama_local
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from cont.dialogue.diagnosis_qa import Reply, ask
from cont.packs.diagnosis.equipment import EquipmentDiagnosis, diagnose_equipment, load_site, site_special
from cont.packs.diagnosis.guidance import guide
from cont.packs.diagnosis.special import interpret
from cont.packs.diagnosis.trend import trend
from cont.view import render_equipment

EXAMPLES = ("이 설비 지금 어떤가요?", "어느 계통이 언제부터 이상했나요?", "구동부 진동이 왜 커졌나요?", "유압 쪽은 무엇을 점검해야 하나요?",
            "가열 구역은 괜찮은가요?")
MAX_BODY = 4000


def source_text(r: Reply) -> str:
    base = "답의 출처: 진단 결과를 LLM이 다듬음" if r.source == "llm" else "답의 출처: 진단 결과에서 규칙으로 만듦 (LLM 없음)"
    return base + (f" · {r.note}" if r.note else "")


def answer_text(r: Reply) -> str:
    """화면에 보일 답. LLM이 다듬은 답에는 근거로 쓴 진단 사실을 그대로 붙여, 읽는 사람이 대조할 수 있게 한다."""
    return r.text if r.source != "llm" else f"{r.text}\n\n근거로 쓴 진단 결과 (LLM이 다듬기 전):\n{r.facts}"


def example_answers(eq: EquipmentDiagnosis, questions: tuple[str, ...] = EXAMPLES, provider: Any | None = None,
                    guidance: Any | None = None) -> list[tuple[str, str, str]]:
    out = []
    for q in questions:
        r = ask(q, eq, provider, guidance)
        out.append((q, answer_text(r), source_text(r)))
    return out


def make_handler(eq: EquipmentDiagnosis, provider: Any | None, title: str, subtitle: str, special: str | None = None):
    it = interpret(special, eq) if special else None
    g = guide(eq, it)
    page = render_equipment(eq, title, subtitle, example_answers(eq, guidance=g), ask_url="/ask", findings=it.findings if it else (),
                            guidance=g, trend=trend(eq)).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/ask":
                return self._send(404, b"not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= MAX_BODY:
                    raise ValueError("bad length")
                q = str(json.loads(self.rfile.read(n)).get("question", "")).strip()
                if not q:
                    raise ValueError("empty question")
            except (ValueError, json.JSONDecodeError, AttributeError):
                return self._send(400, json.dumps({"text": "질문을 읽지 못했습니다.", "source": ""}, ensure_ascii=False).encode(), "application/json")
            r = ask(q, eq, provider, g)
            self._send(200, json.dumps({"text": answer_text(r), "source": source_text(r), "systems": r.systems}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def log_message(self, *_: Any) -> None:
            pass

    return Handler


def make_server(eq: EquipmentDiagnosis, provider: Any | None = None, port: int = 8765, title: str = "설비 공통 이상진단",
                subtitle: str = "", special: str | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(eq, provider, title, subtitle, special))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--llm", nargs="?", const="", default=None, metavar="공급자", help="LLM으로 답의 말을 다듬는다 (이름을 비우면 기본 공급자)")
    a = ap.parse_args(argv)
    if a.site:
        name, systems = load_site(a.site); eq = diagnose_equipment(systems, name); sub = f"현장 설정: {a.site}"
        special = site_special(a.site)
    else:
        special = None
        from cont.packs.diagnosis.demo import synthetic_equipment
        eq = synthetic_equipment(); sub = "가상 설비 시연: 정답을 알고 만든 신호"
    provider = None
    if a.llm is not None:
        from cont.llm import get_provider
        provider = get_provider(a.llm or None)
    srv = make_server(eq, provider, a.port, subtitle=sub, special=special)
    print(f"http://127.0.0.1:{a.port}  (끝내기: Ctrl+C)  LLM: {getattr(provider, 'name', '쓰지 않음')}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
