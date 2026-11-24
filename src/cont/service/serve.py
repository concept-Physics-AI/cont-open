"""서비스 층의 HTTP 서버. 이 컴퓨터(127.0.0.1)에서만 열리고 인증이 없다. 외부 공개는 하지 않는다 (ARCHITECTURE.md "서비스 층")."""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

from cont.service import api

HOST = "127.0.0.1"
_CFG = Path(__file__).resolve().parents[3] / "config" / "service.yaml"


def config() -> dict[str, Any]:
    c = yaml.safe_load(_CFG.read_text(encoding="utf-8"))
    if os.environ.get("CONT_SERVICE_PORT"):
        c["port"] = int(os.environ["CONT_SERVICE_PORT"])
    return c


def make_server(port: int | None = None, host: str = HOST) -> ThreadingHTTPServer:
    if host != HOST:
        raise ValueError("서비스는 127.0.0.1에서만 열 수 있습니다. 외부 공개와 보안 방식은 아직 정하지 않았습니다")
    cfg = config()
    limit = int(cfg["max_body_bytes"])

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: Any) -> None:
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/v1/health":
                return self._send(200, {"ok": True})
            if self.path == "/v1/packs":
                return self._send(200, {"packs": api.list_packs()})
            if self.path in ("/physics", "/"):
                from cont.view.physics_page import render_physics
                b = render_physics(live=True).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b))); self.end_headers()
                return self.wfile.write(b)
            parts = self.path.split("?")[0].strip("/").split("/")
            if parts[:2] == ["v1", "runs"] and len(parts) in (2, 3):
                from urllib.parse import parse_qs, urlparse
                from cont.service import runs
                try:
                    if len(parts) == 3:
                        return self._send(200, api.get_run(parts[2]))
                    q = parse_qs(urlparse(self.path).query)
                    return self._send(200, {"runs": api.list_runs(q.get("pack", [None])[0], int(q.get("limit", ["50"])[0]))})
                except api.NotFound as exc:
                    return self._send(404, {"error": f"없는 실행이거나 저장소가 꺼져 있습니다: {exc}"})
                except runs.RunCorrupt as exc:
                    return self._send(500, {"error": str(exc)})
            self._send(404, {"error": "없는 주소입니다"})

        def do_POST(self) -> None:  # noqa: N802
            parts = self.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "recompute":
                try:
                    return self._send(200, api.recompute(parts[2]))
                except api.NotFound as exc:
                    return self._send(404, {"error": f"없는 실행이거나 저장소가 꺼져 있습니다: {exc}"})
                except Exception as exc:
                    return self._send(400, {"error": f"계산하지 못했습니다: {exc}"})
            if not (len(parts) == 4 and parts[0] == "v1" and parts[1] == "packs"):
                return self._send(404, {"error": "없는 주소입니다"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= limit:
                    return self._send(413, {"error": "요청 본문이 비었거나 너무 큽니다"})
                d = json.loads(self.rfile.read(n))
                self._send(200, api.execute(parts[2], d.get("inputs", {}), str(d.get("question", "")), parts[3],
                                                project_id=str(d.get("project_id", "")), asset_id=str(d.get("asset_id", ""))))
            except api.NotFound:
                self._send(404, {"error": f"'{parts[2]}/{parts[3]}'는 없는 팩이거나 없는 동작입니다", "available": [p['key'] for p in api.list_packs()]})
            except Exception as exc:            # 계산할 수 없는 입력이면 이유를 돌려준다
                self._send(400, {"error": f"계산하지 못했습니다: {exc}"})

        def log_message(self, *_: Any) -> None:
            pass

    return ThreadingHTTPServer((host, int(port if port is not None else cfg["port"])), Handler)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int)
    a = ap.parse_args(argv)
    srv = make_server(a.port)
    print(f"http://{HOST}:{srv.server_address[1]}/v1/health  (끝내기: Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
