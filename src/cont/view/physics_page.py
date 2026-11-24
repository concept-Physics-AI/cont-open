"""ConT Physics 화면: Studio와 FAB이 함께 쓰는 엔진의 목록.

지금 코드에 있는 엔진(config/physics/engines.yaml)과, FAB 진열대에서 아직 엔진이 없는 표현 유형이 기다리는 엔진(config/fab/types.yaml)을 보인다.
엔진을 새로 만들지는 않는다. 값은 엔진이 낸 계산값이며 실측 검증 전이다.
"""
from __future__ import annotations

import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import yaml

from cont.fab.catalog import types_data
from cont.tolerance import CONFIG_DIR
from cont.view.physics_heat import CSS as HC_CSS, render_heat_compare
from cont.view.physics_work import CSS as WB_CSS, render_workbench
from cont.view.switcher import with_switcher


def engines_ready() -> list[dict[str, Any]]:
    with open(CONFIG_DIR / "physics" / "engines.yaml", encoding="utf-8") as f:
        items = (yaml.safe_load(f) or {}).get("engines") or []
    for x in items:
        if not all(x.get(k) for k in ("key", "name", "summary", "limits")):
            raise ValueError(f"engine needs key, name, summary, limits: {x!r}")
    return items


def engines_wanted() -> list[dict[str, Any]]:
    """아직 없는 엔진과, 그것을 기다리는 표현 유형. 기다리는 유형이 많은 순."""
    d = types_data()
    waiting: dict[str, list[str]] = {}
    for t in d["types"]:
        if not t["covered_by"]:
            waiting.setdefault(t["engine"], []).append(t["name"])
    out = [{"key": k, "name": d["engines"][k]["name"], "summary": d["engines"][k]["summary"], "types": v} for k, v in waiting.items()]
    return sorted(out, key=lambda x: (-len(x["types"]), x["name"]))


CSS = """*{box-sizing:border-box}body{margin:0;font-family:'IBM Plex Sans KR',system-ui,sans-serif;color:#1B2229;background:#fff;line-height:1.55}
.pg{max-width:1040px;margin:0 auto;padding:36px 24px 80px}h1{font-size:30px;font-weight:600;letter-spacing:-.02em;margin:0 0 8px}.lead{font-size:15px;color:#59636D;max-width:640px}
h2{font-size:21px;font-weight:600;margin:40px 0 4px}.sub{font-size:13.5px;color:#59636D;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}.card{border:1px solid #DDE2E7;border-radius:16px;padding:16px 18px;background:#fff;display:flex;flex-direction:column;gap:6px}
.card h3{font-size:16px;font-weight:600;margin:0}.card p{margin:0;font-size:13.5px;color:#59636D}.card .lim{font-size:12.5px;color:#8A5A00;background:#FFF3DC;border-radius:8px;padding:6px 10px;margin-top:4px}
.card.want{border-style:dashed;background:#FBFCFD}.card .n{font-size:12.5px;font-weight:600;color:#0B8480}.card ul{margin:2px 0 0;padding-left:18px;font-size:12.5px;color:#59636D}
.note{font-size:12.5px;color:#59636D;margin-top:28px;border-top:1px solid #DDE2E7;padding-top:12px}"""


def render_physics(urls: dict[str, str] | None = None, live: bool = False) -> str:
    e = html.escape
    ready, wanted = engines_ready(), engines_wanted()
    r = "".join(f'<article class="card"><h3>{e(x["name"])}</h3><p>{e(x["summary"])}</p><p class="lim">{e(x["limits"])}</p></article>' for x in ready)
    w = "".join(f'<article class="card want"><h3>{e(x["name"])}</h3><p>{e(x["summary"])}</p><span class="n">기다리는 표현 유형 {len(x["types"])}개</span>'
                f'<ul>{"".join(f"<li>{e(t)}</li>" for t in x["types"][:4])}{"<li>…</li>" if len(x["types"]) > 4 else ""}</ul></article>' for x in wanted)
    body = (f'<main class="pg"><h1>물리·AI 엔진</h1><p class="lead">Studio와 FAB은 같은 엔진을 씁니다. 화면마다 계산을 따로 하지 않고, 물리 값은 여기 있는 엔진만 냅니다.</p>'
            f'{render_workbench(live)}{render_heat_compare()}'
            f'<h2>지금 있는 엔진 {len(ready)}개</h2><p class="sub">코드에 있고 실제로 돌아갑니다. 한계를 함께 적었습니다.</p><div class="grid">{r}</div>'
            f'<h2>아직 없는 엔진 {len(wanted)}개</h2><p class="sub">FAB 진열대에서 "필요해요"로 요청이 쌓이는 곳입니다. 기다리는 유형이 많은 순서입니다.</p><div class="grid">{w}</div>'
            f'<p class="note">엔진이 낸 값은 계산값이며 실측과 대조하기 전입니다. 엔진이 돌았다는 것이 물리적으로 맞다는 뜻은 아닙니다.</p></main>')
    page = (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>ConT Physics</title><style>{CSS}{WB_CSS}{HC_CSS}</style></head><body>\n{body}\n</body></html>')
    return with_switcher(page, "physics", urls)


def make_server(port: int = 8769) -> ThreadingHTTPServer:
    page = render_physics().encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            ok = self.path in ("/", "/index.html")
            body, code = (page, 200) if ok else (b"not found", 404)
            self.send_response(code); self.send_header("Content-Type", "text/html; charset=utf-8" if ok else "text/plain")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="서버를 띄우지 않고 화면을 파일 하나로 쓴다")
    ap.add_argument("--port", type=int, default=8769)
    a = ap.parse_args(argv)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(render_physics())
        print(f"written {a.out}")
        return
    srv = make_server(a.port)
    print(f"ConT Physics: http://127.0.0.1:{a.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
