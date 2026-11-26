"""장면 대화의 계획 품질 측정: 실제 LLM 공급자에 같은 대화를 반복해 성공·실패·거절·소요시간을 기록한다.

한 사례는 새 세션(가짜 생성기)에서 말하고, 최종 상태를 코드가 검사한다(expect 어휘는 config/dialogue/scene_eval.yaml).
이 측정은 계획기(LLM)가 요청을 올바른 도구 호출로 푸는지를 본다. 이미지 모델이나 물리 값은 보지 않는다.
결과는 JSON으로 남기며 제품 목표 수치는 정하지 않는다(첫 기준 측정).
    python -m cont.dialogue.scene_eval --llm ollama_local --out result.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from cont.dialogue.scene_chat import SceneSession
from cont.generation import get_generator
from cont.objspec import ViewState, hybrid_bonding_stack
from cont.tolerance import CONFIG_DIR

_VOCAB = {"unchanged", "speed", "camera", "parts", "selection", "playback_t", "images", "reopen_speed"}


def load_cases(path: Path | None = None) -> dict[str, Any]:
    cfg = yaml.safe_load((path or CONFIG_DIR / "dialogue" / "scene_eval.yaml").read_text(encoding="utf-8"))
    for c in cfg["cases"]:
        bad = set(c["expect"]) - _VOCAB
        if bad or not c.get("turns"):
            raise ValueError(f"사례 '{c.get('id')}': 모르는 expect {sorted(bad)} 또는 turns 없음")
    return cfg


def check(s: SceneSession, init: tuple[Any, ...], expect: dict[str, Any], root: Path) -> list[str]:
    """최종 상태가 기대와 다른 점. 비어 있으면 통과."""
    spec0, view0 = init
    out: list[str] = []
    if expect.get("unchanged"):
        if s.spec != spec0 or s.view != view0 or s.selection or s.playback_t or s.new_images or s.saved_images:
            out.append("바뀌면 안 되는데 상태가 바뀌었다")
        return out
    want_speed = {k: float(v) for k, v in expect.get("speed", {}).items()}
    for st in s.spec.stages:
        got, exp = s.view.speed_of(st.id), want_speed.get(st.id, view0.speed_of(st.id))
        if abs(got - exp) > 1e-9:
            out.append(f"{st.id} 속도 {got} (기대 {exp})")
    cam = {k: float(v) for k, v in expect.get("camera", {}).items()}
    for f in ("azimuth", "elevation", "distance"):
        got, exp = getattr(s.view, f), cam.get(f, getattr(view0, f))
        if abs(got - exp) > 1e-9:
            out.append(f"카메라 {f} {got} (기대 {exp})")
    want_parts = expect.get("parts", {})
    for pid in s.spec.part_ids:
        a, b = spec0.part(pid).part, s.spec.part(pid).part
        for f in ("name", "z0", "z1", "outer", "inner"):
            exp = want_parts.get(pid, {}).get(f, getattr(a, f))
            if getattr(b, f) != exp and not (isinstance(exp, (int, float)) and abs(getattr(b, f) - exp) < 1e-9):
                out.append(f"{pid}.{f} {getattr(b, f)} (기대 {exp})")
    if "selection" in expect and list(s.selection) != list(expect["selection"]):
        out.append(f"선택 {list(s.selection)} (기대 {expect['selection']})")
    if abs(s.playback_t - float(expect.get("playback_t", 0.0))) > 1e-9:
        out.append(f"재생 위치 {s.playback_t} (기대 {expect.get('playback_t', 0.0)})")
    n = len(s.new_images) + len(s.saved_images)
    if n != int(expect.get("images", 0)):
        out.append(f"이미지 {n}개 (기대 {expect.get('images', 0)})")
    if "reopen_speed" in expect:
        try:
            re = SceneSession.open(root / "proj", get_generator("fake"), None)
            for sid, f in expect["reopen_speed"].items():
                if abs(re.view.speed_of(sid) - float(f)) > 1e-9:
                    out.append(f"다시 연 프로젝트의 {sid} 속도 {re.view.speed_of(sid)} (기대 {f})")
        except Exception as e:                                           # 저장되지 않았거나 열 수 없음
            out.append(f"다시 열지 못함: {type(e).__name__}")
    return out


def run_case(case: dict[str, Any], provider: Any, opts: dict[str, Any]) -> dict[str, Any]:
    spec = hybrid_bonding_stack()
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        s = SceneSession(spec, get_generator("fake"), provider, root=root / "proj", project_id="eval", name="eval", llm_opts=opts)
        turns = []
        for text in case["turns"]:
            t0 = time.monotonic()
            t = s.turn(text)
            turns.append({"text": text, "kind": t.kind, "seconds": round(time.monotonic() - t0, 2), "reply": t.reply[:300],
                          "steps": [(x["tool"], x["state"]) for x in t.steps]})
        fails = check(s, (spec, ViewState()), case["expect"], root)
    return {"id": case["id"], "passed": not fails, "failures": fails, "turns": turns}


def run(provider: Any, cfg: dict[str, Any], only: list[str] | None = None, repeat: int | None = None) -> dict[str, Any]:
    n = repeat or cfg["repeat"]
    if hasattr(provider, "timeout"):
        provider.timeout = cfg.get("timeout_s", provider.timeout)
    rows = []
    for case in cfg["cases"]:
        if only and case["id"] not in only:
            continue
        for k in range(n):
            r = run_case(case, provider, cfg.get("llm_opts", {}))
            r["trial"] = k + 1
            rows.append(r)
    secs = [t["seconds"] for r in rows for t in r["turns"]]
    kinds = [t["kind"] for r in rows for t in r["turns"]]
    per = {}
    for r in rows:
        p = per.setdefault(r["id"], {"trials": 0, "passed": 0})
        p["trials"] += 1
        p["passed"] += r["passed"]
    return {"provider": getattr(provider, "name", "?"), "model": getattr(provider, "model", "?"), "repeat": n,
            "trials": len(rows), "passed": sum(r["passed"] for r in rows),
            "turn_kinds": {k: kinds.count(k) for k in sorted(set(kinds))},
            "seconds": {"median": round(statistics.median(secs), 2), "max": max(secs)} if secs else {},
            "per_case": per, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    from cont.llm import get_provider
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--llm", default=None)
    ap.add_argument("--repeat", type=int, default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cases", default=None, help="사례 파일 (기본 config/dialogue/scene_eval.yaml)")
    a = ap.parse_args(argv)
    res = run(get_provider(a.llm), load_cases(Path(a.cases) if a.cases else None), a.only, a.repeat)
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
