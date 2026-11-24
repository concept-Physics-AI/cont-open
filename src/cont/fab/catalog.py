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
        if it.get("own", "") not in ("", "spectrum", "spectrogram", "values"):
            raise ValueError(f"catalog item {it['key']!r} has an unknown 'own' mode")
        keys.add(it["key"])
    for it in items:
        if [k for k in it.get("together") or [] if k not in keys]:
            raise ValueError(f"catalog item {it['key']!r} points to an unknown item in 'together'")
    sets = data.get("sets") or []
    for s in sets:
        if [k for k in s["items"] if k not in keys]:
            raise ValueError(f"catalog set {s['key']!r} names an unknown item")
    return {"forms": forms, "uses": uses, "quantities": data.get("quantities") or [], "items": items, "sets": sets, "rule": data.get("sample_rule") or {}}


def own_sample(key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """올린 CSV로 카드 샘플 하나를 만든다 (own이 있는 상품만)."""
    from cont.fab.own_signal import analyze
    it = next((i for i in load()["items"] if i["key"] == key), None)
    if it is None or not it.get("own"):
        raise ValueError("이 카드는 내 신호를 받지 않습니다")
    return _sample(analyze(it["own"], payload))


def _sample(s: Mapping[str, Any]) -> dict[str, Any]:
    """샘플 하나. view3d(3D를 돌려 볼 때 쓰는 값)와 more(근거 자세히)는 있을 때만 붙는다."""
    out = {"label": s["label"], "html": s["html"], "facts": [list(x) for x in s["facts"]], "params": s.get("params") or {}}
    for k in ("view3d", "more", "own"):
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
        out.append({**{k: it[k] for k in SHOWN}, "form_label": data["forms"][it["form"]], "doc": it.get("doc", ""), "own": it.get("own", ""), "preview_note": it.get("preview_note", ""),
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


TYPE_REQUIRED = ("key", "form", "group", "name", "shows", "controls", "quantity", "uses")
TYPE_OPEN = ("engine", "sketch", "needs", "ready")           # 엔진이 없는 유형(준비 중 카드)에 꼭 있어야 하는 것


@lru_cache(maxsize=1)
def _types_yaml() -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / "fab" / "types.yaml").read_text(encoding="utf-8"))


def types_data() -> dict[str, Any]:
    """표현 유형 목록. 엔진이 없는 유형은 개념도(선으로 그린 예시 그림)가 붙는다. covered_by가 있으면 지금 그 상품으로 되는 것이다."""
    from cont.fab.sketches import SKETCHES, sketch
    raw, cat = _types_yaml(), load()
    forms, quantities, uses = cat["forms"], set(cat["quantities"]), set(cat["uses"])
    item_keys = {i["key"] for i in cat["items"]}
    engines = raw["engines"]
    for k, e in engines.items():
        if not (e.get("name") and e.get("summary")):
            raise ValueError(f"engine {k!r} needs name and summary")
    out, seen = [], set()
    for t in raw["types"]:
        miss = [k for k in TYPE_REQUIRED if not t.get(k)]
        if miss or t["key"] in seen:
            raise ValueError(f"type {t.get('key')!r}: missing {miss} or duplicate key")
        seen.add(t["key"])
        if t["form"] not in forms or t["quantity"] not in quantities or not set(t["uses"]) <= uses:
            raise ValueError(f"type {t['key']!r} uses an unknown form, quantity or use")
        covered = list(t.get("covered_by") or [])
        if not set(covered) <= item_keys:
            raise ValueError(f"type {t['key']!r} names an unknown item in covered_by")
        if not covered:
            if any(not t.get(k) for k in TYPE_OPEN) or t["engine"] not in engines or t["sketch"] not in SKETCHES:
                raise ValueError(f"type {t['key']!r} has no engine yet, so it needs engine, sketch, needs and ready")
            if t["sketch"] in ("calc", "judge") and len(t.get("args") or []) != 3:
                raise ValueError(f"type {t['key']!r}: sketch {t['sketch']} needs three args")
        svg = "" if covered else sketch(t["sketch"], t["name"], t.get("args") or ())
        out.append({"key": t["key"], "form": t["form"], "form_label": forms[t["form"]], "group": t["group"], "name": t["name"], "shows": t["shows"],
                    "controls": list(t["controls"]), "quantity": t["quantity"], "uses": list(t["uses"]), "covered_by": covered, "note": t.get("note", ""),
                    "engine": "" if covered else t["engine"], "engine_name": "" if covered else engines[t["engine"]]["name"],
                    "needs": t.get("needs", ""), "ready": t.get("ready", ""), "sketch_svg": svg})
    return {"engines": {k: dict(v) for k, v in engines.items()}, "types": out}


def set_condition(items: Sequence[Mapping[str, Any]], one_set: Mapping[str, Any]) -> dict[str, Any]:
    """세트를 담을 때 쓸 조건. 같은 대상(규격)의 결과가 모든 상품에 있으면 그 조건으로 묶고(common),
    없으면 서로 다른 조건의 비교용으로 담김을 알린다(mixed). 조건 변수가 없는 상품만 있으면 none.
    표기만 맞추지 않는다: 각 상품에서 실제로 계산해 둔 샘플만 고른다."""
    by_key = {i["key"]: i for i in items}
    members = [by_key[k] for k in one_set["items"] if k in by_key]
    sized = [m for m in members if any((s.get("params") or {}).get("size") for s in m["samples"])]
    if not sized:
        return {"mode": "none", "pick": {}, "note": ""}
    sizes = [[(s.get("params") or {}).get("size") for s in m["samples"]] for m in sized]
    common = [z for z in dict.fromkeys(sizes[0]) if z and all(z in x for x in sizes)]
    if common:
        z = common[0]
        pick = {m["key"]: next(i for i, s in enumerate(m["samples"]) if (s.get("params") or {}).get("size") == z) for m in sized}
        lab = next(s["label"] for s in sized[0]["samples"] if (s.get("params") or {}).get("size") == z)
        return {"mode": "common", "pick": pick, "note": f"같은 대상과 조건({lab})으로 담습니다"}
    pick = {m["key"]: 0 for m in sized}
    conds = ", ".join(f'{m["name"]} {m["samples"][0]["label"]}' for m in sized)
    return {"mode": "mixed", "pick": pick, "note": f"공통으로 쓸 규격이 없어 서로 다른 조건의 비교용으로 담습니다 ({conds})"}
