"""고를 수 있는 물리 정보의 목록. config/fab/catalog.yaml을 읽고, 상품마다 엔진을 돌린 샘플을 붙인다."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

import yaml

from cont.tolerance import CONFIG_DIR

REQUIRED = ("key", "name", "short", "form", "area", "quantity", "summary", "needs", "gives", "preview", "uses", "limits")
SHOWN = ("key", "name", "short", "form", "area", "quantity", "summary", "needs", "gives", "uses", "limits")


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    with open(CONFIG_DIR / "fab" / "catalog.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    forms, items, uses = data.get("forms") or {}, data.get("items") or [], data.get("uses") or []
    keys: set[str] = set()
    for it in items:
        missing = [k for k in REQUIRED if not it.get(k)]
        if missing:
            raise ValueError(f"catalog item {it.get('key')!r} lacks {missing}")
        if it["key"] in keys:
            raise ValueError(f"duplicate catalog key {it['key']!r}")
        if it["form"] not in forms:
            raise ValueError(f"catalog item {it['key']!r} has unknown form {it['form']!r}")
        if it["quantity"] not in (data.get("quantities") or []):
            raise ValueError(f"catalog item {it['key']!r} has unknown quantity {it['quantity']!r}")
        if [u for u in it["uses"] if u not in uses]:
            raise ValueError(f"catalog item {it['key']!r} has an unknown use")
        keys.add(it["key"])
    for it in items:
        if [k for k in it.get("together") or [] if k not in keys]:
            raise ValueError(f"catalog item {it['key']!r} points to an unknown item in 'together'")
    sets = data.get("sets") or []
    for s in sets:
        if [k for k in s["items"] if k not in keys]:
            raise ValueError(f"catalog set {s['key']!r} names an unknown item")
    return {"forms": forms, "uses": uses, "quantities": data.get("quantities") or [], "items": items, "sets": sets, "rule": data.get("sample_rule") or {}}


def _sample(s: Mapping[str, Any]) -> dict[str, Any]:
    """샘플 하나. view3d(3D를 돌려 볼 때 쓰는 값)와 more(근거 자세히)는 있을 때만 붙는다."""
    out = {"label": s["label"], "html": s["html"], "facts": [list(x) for x in s["facts"]], "params": s.get("params") or {}}
    for k in ("view3d", "more"):
        if s.get(k):
            out[k] = s[k]
    return out


def meshes(items: Sequence[Mapping[str, Any]], digits: int = 1) -> dict[str, Any]:
    """3D 샘플이 쓰는 규격별 삼각형 자료 (화면에서 돌려 보기용). 소수 첫째 자리까지만 싣는다."""
    from cont.fab.previews import joint_for
    sizes = sorted({s["view3d"]["size"] for it in items for s in it["samples"] if s.get("view3d")})
    out = {}
    for size in sizes:
        v = joint_for(size)["state"]["viewer"]
        out[size] = {"c": [round(x, 3) for x in v["center"]], "r": round(v["radius"], 3),
                     "p": [{"r": p["role"], "t": [round(x, digits) for x in p["tri"]]} for p in v["parts"]]}
    return out


def catalog() -> list[dict[str, Any]]:
    """상품들. 상품마다 엔진을 조건별로 돌린 샘플(samples)이 붙는다."""
    from cont.fab.previews import MAKEABLE, PREVIEWS
    data = load()
    out = []
    for it in data["items"]:
        if it["preview"] not in PREVIEWS:
            raise ValueError(f"catalog item {it['key']!r} names an unknown preview {it['preview']!r}")
        samples = PREVIEWS[it["preview"]](it)
        if not samples:
            raise ValueError(f"catalog item {it['key']!r} produced no sample")
        out.append({**{k: it[k] for k in SHOWN}, "form_label": data["forms"][it["form"]], "doc": it.get("doc", ""), "preview_note": it.get("preview_note", ""),
                    "together": list(it.get("together") or []), "makeable": it["preview"] in MAKEABLE,
                    "samples": [_sample(s) for s in samples]})
    return out


def make(key: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """조건을 받아 샘플 하나를 그 자리에서 만든다 (규격과 조임 토크를 받는 상품만)."""
    from cont.fab.previews import MAKEABLE, PREVIEWS
    it = next((i for i in load()["items"] if i["key"] == key), None)
    if it is None or it["preview"] not in MAKEABLE:
        raise ValueError(f"{key!r} cannot be made on request")
    size = str(params.get("size", "")).strip().upper()
    torque = params.get("torque")
    torque = None if torque in (None, "") else float(torque)
    if torque is not None and torque <= 0:
        raise ValueError("torque must be positive")
    s = PREVIEWS[it["preview"]](it, {"size": size, "torque": torque})[0]
    return _sample(s)


def selection(keys: list[str], site: str = "") -> dict[str, Any]:
    """바구니: 고른 상품으로 만든 '내 Fab'의 씨앗. 꾸리기 화면이 이것을 읽어 시작한다 (꾸리기 화면은 아직 없다)."""
    known = {i["key"]: i for i in load()["items"]}
    unknown = [k for k in keys if k not in known]
    if unknown:
        raise ValueError(f"unknown catalog keys: {unknown}")
    picked = list(dict.fromkeys(keys))
    return {"format": "cont-fab-selection", "version": 1, "site": site,
            "items": [{"key": k, "name": known[k]["name"], "needs": known[k]["needs"]} for k in picked]}
