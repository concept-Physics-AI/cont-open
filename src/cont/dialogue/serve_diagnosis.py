"""설비 이상진단 화면(ConT Fab으로 만든 화면의 한 예)을 내 PC에서 띄우는 작은 서버 (표준 라이브러리만 사용, 127.0.0.1에서만 받는다).

가상 설비로:        python -m cont.dialogue.serve_diagnosis
LLM으로 답 다듬기:  python -m cont.dialogue.serve_diagnosis --llm
파일 하나로:        python -m cont.dialogue.serve_diagnosis --out diagnosis.html      (질문은 미리 만든 답만)
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from cont.dialogue.diagnosis_qa import ask
from cont.packs.diagnosis import synthetic
from cont.packs.diagnosis.demo import synthetic_equipment
from cont.packs.diagnosis.equipment import EquipmentDiagnosis, diagnose_equipment
from cont.packs.diagnosis.guidance import Guidance, guide
from cont.packs.diagnosis.report import report
from cont.packs.diagnosis.special import interpret
from cont.view.diagnosis_app import case, render_diagnosis_app

MAX_BODY = 4000
QUESTIONS = ("어디가 평소와 다른가요?", "언제부터 달라졌나요?", "원인이 무엇인가요?", "무엇부터 점검해야 하나요?")


def synthetic_cutting() -> tuple[EquipmentDiagnosis, Any]:
    """가상 절삭 설비: 주축 부하가 서서히 커지다가 갑자기 떨어진다 (정답을 알고 만든 신호)."""
    cut = synthetic.inject(synthetic.drive(2000, seed=42), "current", 500, 1400, 1.0, ramp=True)
    cut = synthetic.inject(cut, "current", 1400, 2000, -1.6)
    eq = diagnose_equipment([{"name": "주축", "module": "drive", "normal": synthetic.drive(3000, seed=41), "current": cut, "time": "t",
                              "signals": {"current": "current", "vibration": "vibration"},
                              "conditions": {"load": "load", "speed": "speed"}}], equipment="가상 절삭 설비",
                            question="주축에서 무슨 일이 있었는가?")
    return eq, interpret("cutting", eq, "주축에서 무슨 일이 있었는가?")


def demo_cases(provider: Any | None = None) -> tuple[list[dict[str, Any]], dict[str, tuple[EquipmentDiagnosis, Guidance]]]:
    """화면에 싣는 가상 설비 둘과, 질문에 답할 때 쓰는 진단 결과."""
    cut, it = synthetic_cutting()
    eq = synthetic_equipment()
    made = {"cutting": (cut, guide(cut, it), it, "공구 상태 이상진단"), "equipment": (eq, guide(eq), None, "계통별 이상진단")}
    cases, kept = [], {}
    for cid, (e, g, interp, heading) in made.items():
        qs = []
        for q in QUESTIONS:
            r = ask(q, e, provider, g)
            qs.append((q, r.text, "답을 만든 방법: " + ("LLM" if r.source == "llm" else "규칙 (LLM 없음)")))
        cases.append(case(cid, heading, e, report(e, interp, g), qs, synthetic=True))
        kept[cid] = (e, g)
    return cases, kept


def make_server(port: int = 8767, provider: Any | None = None) -> ThreadingHTTPServer:
    cases, kept = demo_cases()
    page = render_diagnosis_app(cases, "/ask").encode("utf-8")

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
                data = json.loads(self.rfile.read(n))
                question, cid = str(data.get("question", "")).strip(), str(data.get("case", ""))
                if not question or cid not in kept:
                    raise ValueError("bad request")
            except (ValueError, json.JSONDecodeError, AttributeError):
                return self._send(400, json.dumps({"answer": "질문을 읽지 못했습니다."}, ensure_ascii=False).encode(), "application/json")
            e, g = kept[cid]
            r = ask(question, e, provider, g)
            src = "답을 만든 방법: " + ("LLM" if r.source == "llm" else "규칙 (LLM 없음)") + (f" · {r.note}" if getattr(r, "note", "") else "")
            self._send(200, json.dumps({"answer": r.text, "source": src}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, *_: Any) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--llm", nargs="?", const="", default=None, metavar="공급자")
    ap.add_argument("--out", help="서버를 띄우지 않고 화면을 파일 하나로 쓴다")
    a = ap.parse_args(argv)
    provider = None
    if a.llm is not None:
        from cont.llm import get_provider
        provider = get_provider(a.llm or None)
    if a.out:
        cases, _ = demo_cases()
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(render_diagnosis_app(cases))
        print(f"written {a.out}: {len(cases)} case(s), {sum(len(c['cards']) for c in cases)} finding(s)")
        return
    srv = make_server(a.port, provider)
    print(f"http://127.0.0.1:{a.port}  (끝내기: Ctrl+C)  LLM: {getattr(provider, 'name', '쓰지 않음')}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
