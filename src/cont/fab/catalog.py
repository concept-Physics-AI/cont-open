"""고를 수 있는 물리 정보의 목록. config/fab/catalog.yaml을 읽고, 항목마다 엔진을 돌린 미리보기를 붙인다."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from cont.tolerance import CONFIG_DIR

REQUIRED = ("key", "name", "form", "area", "summary", "needs", "gives", "preview")


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    with open(CONFIG_DIR / "fab" / "catalog.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    forms, items = data.get("forms") or {}, data.get("items") or []
    seen: set[str] = set()
    for it in items:
        missing = [k for k in REQUIRED if not it.get(k)]
        if missing:
            raise ValueError(f"catalog item {it.get('key')!r} lacks {missing}")
        if it["key"] in seen:
            raise ValueError(f"duplicate catalog key {it['key']!r}")
        if it["form"] not in forms:
            raise ValueError(f"catalog item {it['key']!r} has unknown form {it['form']!r}")
        seen.add(it["key"])
    return {"forms": forms, "items": items}


def catalog() -> list[dict[str, Any]]:
    """목록의 항목들. 항목마다 엔진을 예제 값으로 돌린 미리보기(preview_html)와 그때의 값(facts)이 붙는다."""
    from cont.fab.previews import PREVIEWS
    data = load()
    out = []
    for it in data["items"]:
        if it["preview"] not in PREVIEWS:
            raise ValueError(f"catalog item {it['key']!r} names an unknown preview {it['preview']!r}")
        p = PREVIEWS[it["preview"]]()
        out.append({**{k: it[k] for k in ("key", "name", "form", "area", "summary", "needs", "gives")}, "form_label": data["forms"][it["form"]],
                    "doc": it.get("doc", ""), "preview_note": it.get("preview_note", ""), "preview_html": p["html"], "facts": [list(x) for x in p["facts"]]})
    return out


def selection(keys: list[str], site: str = "") -> dict[str, Any]:
    """바구니: 고른 항목으로 만든 '내 Fab'의 씨앗. 꾸리기 화면이 이것을 읽어 시작한다 (꾸리기 화면은 아직 없다)."""
    known = {i["key"]: i for i in load()["items"]}
    unknown = [k for k in keys if k not in known]
    if unknown:
        raise ValueError(f"unknown catalog keys: {unknown}")
    picked = list(dict.fromkeys(keys))
    return {"format": "cont-fab-selection", "version": 1, "site": site,
            "items": [{"key": k, "name": known[k]["name"], "needs": known[k]["needs"]} for k in picked]}
