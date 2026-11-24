"""Studio의 열(열전도) 대화: 말에서 가상 입력 조건을 읽고, 계산은 열 팩이 한다.

원칙 (ARCHITECTURE.md "LLM과 숫자")
- 입력 조건(열확산계수, 시간, 길이, 경계 온도, 기준 문제 종류)만 규칙 또는 LLM이 제안한다. 결과의 숫자는 열 팩이 낸다.
- LLM이 제안한 값은 "LLM이 제안한 가상 입력"이라고 밝히고, 허용한 항목·범위가 아니면 버리고 버렸다고 알린다.
- 말하지 않은 조건은 열 팩의 기본 기준 문제 값을 쓰고 그렇다고 알린다. 답은 해석해가 있는 합성 기준 문제이며 실측 대조 전이다.
- LLM은 cont.llm 어댑터로만 부른다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from cont import packs
from cont.answer import PhysicsAnswer
from cont.llm import Message
from cont.packs.heat.pack import CASES, DEFAULTS

NUM = r"(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
# 제안할 수 있는 입력: 키 → (이름, 단위, 허용 범위)
ALLOWED = {"diffusivity": ("열확산계수", "m^2/s", (1e-9, 1e-2)), "duration": ("계산 시간", "s", (1e-3, 1e5)),
           "length": ("길이", "m", (1e-4, 10.0)), "t_wall": ("경계 온도", "K", (1.0, 5000.0)),
           "amplitude": ("처음 온도 진폭", "K", (1e-3, 2000.0)), "t_initial": ("처음 온도", "K", (1.0, 5000.0))}

SYSTEM_PROMPT = (
    "너는 열전도 문제를 가상으로 풀어 보려는 사용자의 말에서 입력 조건만 읽는다. JSON 객체 하나로만 답하고 설명을 붙이지 않는다.\n"
    "쓸 수 있는 키: case(\"sine_1d\" 사인 모양 처음 온도의 1차원 판, \"step_1d\" 처음 온도가 고른 1차원 판, \"sine_2d\" 2차원 직사각형), "
    "diffusivity(m^2/s), duration(s), length(m), t_wall(K, 경계 온도), amplitude(K), t_initial(K).\n"
    "사용자가 말하지 않은 키는 쓰지 않는다. 온도는 켈빈으로, 길이는 미터로 바꾼다. 계산 결과를 만들지 않는다. 바꿀 것이 없으면 {} 를 답한다."
)


@dataclass(frozen=True)
class Proposal:
    inputs: dict[str, Any]              # 열 팩에 줄 입력 (제안된 것만)
    source: str                         # "rule" | "llm"
    dropped: tuple[str, ...] = ()       # 허용하지 않아 버린 항목과 이유
    note: str = ""


def _clean(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out: dict[str, Any] = {}
    dropped: list[str] = []
    for k, v in raw.items():
        if k == "case":
            if v in CASES:
                out[k] = v
            else:
                dropped.append(f"case={v!r}: 알 수 없는 기준 문제")
        elif k in ALLOWED:
            name, _, (lo, hi) = ALLOWED[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= float(v) <= hi:
                dropped.append(f"{name}={v!r}: 숫자이고 {lo:g}~{hi:g} 안이어야 한다")
            else:
                out[k] = float(v)
        else:
            dropped.append(f"{k}: 쓸 수 없는 항목")
    return out, dropped


def parse(text: str) -> dict[str, Any]:
    """말에서 입력 조건을 규칙으로 읽는다."""
    out: dict[str, Any] = {}
    if re.search(r"2\s*차원|이차원|직사각|사각형", text):
        out["case"] = "sine_2d"
    elif re.search(r"고르게|균일|일정한\s*온도|계단|급냉|급가열", text):
        out["case"] = "step_1d"
    m = re.search(rf"(?:열\s*)?확산\s*계수\s*(?:를|은|는|이|가)?\s*{NUM}", text) or re.search(rf"α\s*(?:를|은|는|=)?\s*{NUM}", text)
    if m:
        out["diffusivity"] = float(m.group(1))
    m = re.search(rf"{NUM}\s*(?:초|s\b)", text)
    if m:
        out["duration"] = float(m.group(1))
    m = re.search(rf"(?:길이|두께|폭)\s*(?:를|은|는|이|가)?\s*{NUM}\s*(mm|cm|m)\b", text)
    if m:
        out["length"] = float(m.group(1)) * {"mm": 1e-3, "cm": 1e-2, "m": 1.0}[m.group(2)]
    m = re.search(rf"(?:경계|벽|양\s*끝)\s*온도\s*(?:를|은|는|이|가)?\s*{NUM}\s*(K|켈빈|℃|도)", text)
    if m:
        out["t_wall"] = float(m.group(1)) + (0.0 if m.group(2) in ("K", "켈빈") else 273.15)
    m = re.search(rf"(?:처음|초기)\s*온도\s*(?:를|은|는|이|가)?\s*{NUM}\s*(K|켈빈|℃|도)", text)
    if m:
        v = float(m.group(1)) + (0.0 if m.group(2) in ("K", "켈빈") else 273.15)
        if out.get("case") == "step_1d":
            out["t_initial"] = v
        elif v > out.get("t_wall", DEFAULTS["t_wall"]):          # 사인형: 처음 온도의 최고점이 경계 온도보다 얼마나 높은가
            out["amplitude"] = v - out.get("t_wall", DEFAULTS["t_wall"])
    return out


def propose(text: str, provider: Any | None = None) -> Proposal:
    """입력 조건 제안. LLM이 있으면 LLM이 제안하고 검증하며, 못 쓰면 규칙으로 읽는다."""
    if provider is not None:
        try:
            r = provider.complete([Message("system", SYSTEM_PROMPT), Message("user", text)])
            m = re.search(r"\{.*\}", r.text or "", re.S)
            raw = json.loads(m.group(0) if m else "")
            if not isinstance(raw, dict):
                raise ValueError("not an object")
            inputs, dropped = _clean(raw)
            return Proposal(inputs, "llm", tuple(dropped))
        except Exception as exc:
            inputs, dropped = _clean(parse(text))
            return Proposal(inputs, "rule", tuple(dropped), f"LLM의 답을 쓸 수 없어 규칙으로 읽음 ({type(exc).__name__})")
    inputs, dropped = _clean(parse(text))
    return Proposal(inputs, "rule", tuple(dropped))


def _given_line(p: Proposal) -> str:
    parts = []
    if "case" in p.inputs:
        parts.append(f"기준 문제 {p.inputs['case']}")
    for k, (name, unit, _) in ALLOWED.items():
        if k in p.inputs:
            parts.append(f"{name} {p.inputs[k]:g} {unit}")
    return ", ".join(parts) if parts else "말씀하신 조건 없음"


def source_text(p: Proposal) -> str:
    who = "입력 조건을 LLM이 제안한 가상 입력으로 읽음 (계산은 열 팩)" if p.source == "llm" else "입력 조건을 규칙으로 읽음 (LLM 없음, 계산은 열 팩)"
    return "답의 출처: " + who + (f" · {p.note}" if p.note else "")


def numbers(a: PhysicsAnswer) -> tuple[float, float, float | None]:
    return a.value("peak_temperature"), a.value("deviation_rms"), a.value("grid_order")


def reply(text: str, provider: Any | None = None) -> dict[str, Any]:
    """대화 화면에 보내는 한 번의 답 (체결 대화와 같은 모양, 상태는 없다)."""
    p = propose(text, provider)
    inputs = dict(p.inputs)
    try:
        a = packs.get("heat").solve(inputs, text)
    except ValueError as exc:
        body = f"그 조건으로는 계산하지 못했습니다.\n이유: {exc}"
        return _shape(body, body + "\n\n" + source_text(p))
    peak, rms, order = numbers(a)
    used = _given_line(p)
    unsaid = "" if p.inputs else " 조건을 말씀하지 않아 열 팩의 기본 기준 문제 값으로 계산했습니다."
    lines = [
        f"가상 입력으로 비정상 열전도를 계산했습니다 ({used}).{unsaid}",
        f"마지막 시각의 최고 온도는 {peak:.2f} K이고, 해석해와의 편차는 RMS {rms:.2g} K입니다."
        + (f" 격자 수렴 차수는 {order:.2f}입니다." if order is not None else ""),
        "해석해가 있는 합성 기준 문제이며 실측과 대조하지 않았습니다. 편차가 허용되는지는 판정하지 않습니다.",
    ]
    if p.dropped:
        lines.append("쓰지 않은 제안: " + "; ".join(p.dropped))
    body = "\n".join(lines)
    return _shape(body, body + "\n\n" + source_text(p) + "\n" + a.truth_line())


def _shape(talk_text: str, detail: str) -> dict[str, Any]:
    return {"state": None, "talk": {"text": talk_text, "alert": None, "alert_low": False}, "brief": None, "ui": None, "detail": detail,
            "suggest": ["열확산계수 2e-4로 해 줘", "2차원 판으로 계산해 줘", "처음 온도가 고른 판은 어때?"]}
