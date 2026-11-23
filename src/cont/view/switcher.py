"""화면 맨 위의 Studio · Physics · FAB 전환 틀.

세 제품은 서버가 따로 돌아도 같은 틀을 달고 나온다. 이름과 주소는 config/products.yaml이 정하고,
주소는 환경 변수로 바꿀 수 있다. 주소를 모르는 제품은 눌러도 이동하지 않고 그렇다고 알린다.
"""
from __future__ import annotations

import html
import os
from functools import lru_cache
from typing import Any, Mapping

import yaml

from cont.tolerance import CONFIG_DIR

HEIGHT = 40
SWITCHER_CSS = f""":root{{--psw:{HEIGHT}px}}body{{padding-top:var(--psw)}}
.psw{{position:fixed;left:0;right:0;top:0;z-index:40;height:var(--psw);display:flex;align-items:center;gap:6px;padding:0 14px;background:#14181D;color:#EEF1F4;font-family:inherit}}
.psw .psn{{font-size:14px;font-weight:600;margin-right:10px;white-space:nowrap}}.psw nav{{display:flex;gap:4px}}
.psw a,.psw span.tab{{display:flex;align-items:center;height:30px;padding:0 14px;border-radius:15px;font-size:13.5px;color:#C9D0D7;text-decoration:none;white-space:nowrap}}
.psw a:hover{{background:#232A32}}.psw [aria-current=page]{{background:#EEF1F4;color:#14181D;font-weight:600}}.psw span.tab{{color:#8A929B;cursor:default}}
.psw .psr{{margin-left:auto;font-size:12.5px;color:#A3ABB4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}}
.psw a:focus-visible{{outline:2px solid #5ED1CB;outline-offset:1px}}
.fab,.app.app{{height:calc(100dvh - var(--psw))}}.top{{top:var(--psw)!important}}
@media(max-width:760px){{.psw .psr{{display:none}}.psw .psn{{display:none}}}}"""


@lru_cache(maxsize=1)
def _products() -> list[dict[str, Any]]:
    with open(CONFIG_DIR / "products.yaml", encoding="utf-8") as f:
        items = (yaml.safe_load(f) or {}).get("products") or []
    for p in items:
        if not (p.get("key") and p.get("name") and p.get("role")):
            raise ValueError(f"product needs key, name and role: {p!r}")
    if [p["key"] for p in items] != ["studio", "physics", "fab"]:
        raise ValueError("products.yaml must list studio, physics, fab in this order")
    return items


def product_urls() -> dict[str, str]:
    """제품 키 → 주소. 환경 변수가 있으면 그것을, 없으면 설정 파일의 기본값을 쓴다."""
    return {p["key"]: os.environ.get(p.get("url_env", ""), p.get("default_url", "")) or "" for p in _products()}


def switcher_html(current: str, urls: Mapping[str, str] | None = None) -> str:
    items = _products()
    if current not in {p["key"] for p in items}:
        raise KeyError(f"unknown product {current!r}")
    urls = dict(product_urls(), **(urls or {}))
    e = html.escape
    tabs, role = [], ""
    for p in items:
        if p["key"] == current:
            tabs.append(f'<a aria-current="page" href="{e(urls[p["key"]] or "#")}">{e(p["name"])}</a>')
            role = p["role"]
        elif urls.get(p["key"]):
            tabs.append(f'<a href="{e(urls[p["key"]])}" title="{e(p["role"])}">{e(p["name"])}</a>')
        else:
            tabs.append(f'<span class="tab" title="{e(p["name"])}의 주소가 정해지지 않았습니다">{e(p["name"])}</span>')
    return f'<div class="psw" role="banner"><span class="psn">ConT</span><nav aria-label="제품 전환">{"".join(tabs)}</nav><span class="psr">{e(role)}</span></div>'


def with_switcher(page: str, current: str, urls: Mapping[str, str] | None = None) -> str:
    """완성된 HTML 한 장에 전환 틀을 단다 (CSS는 첫 <style> 끝에, 막대는 <body> 바로 뒤에)."""
    if "</style>" not in page or "<body>" not in page:
        raise ValueError("page needs a <style> block and a <body> tag")
    return page.replace("</style>", SWITCHER_CSS + "</style>", 1).replace("<body>", "<body>\n" + switcher_html(current, urls), 1)
