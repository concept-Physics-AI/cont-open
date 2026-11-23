"""체결 조인트를 대화로 바꾸기.

원칙
- 말에서 "무엇을 얼마로 바꿀지"만 뽑는다. 계산은 체결 팩이 다시 한다. LLM이 숫자 결과를 만들지 않는다.
- LLM 없이도 된다 (규칙으로 읽는다). LLM을 쓰면 LLM은 바꿀 항목을 JSON으로만 답하고, 허용한 항목·형식이 아니면 버리고 규칙으로 읽는다.
- 바꿀 수 없는 값(표준 데이터에 없는 규격 등)이면 조인트를 그대로 두고 이유를 말한다.
- LLM은 cont.llm 어댑터로만 부른다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any

from cont.answer import PhysicsAnswer
from cont.llm import Message
from cont.packs.fastening import standards
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.packs.fastening.pack import answer as solve
from cont.packs.fastening.recommend import TARGETS, Candidate, recommend, torque_span

NUM = r"(\d+(?:\.\d+)?)"
# (바꿀 항목, 사람이 읽는 이름, 단위, 이 항목을 가리키는 말)
JOINT_FIELDS = {
    "plate_head_thickness": ("머리 쪽 판 두께", "mm", r"머리\s*쪽?\s*판(?:\s*두께)?"),
    "plate_nut_thickness": ("너트 쪽 판 두께", "mm", r"너트\s*쪽?\s*판(?:\s*두께)?"),
    "outer_diameter": ("바깥지름", "mm", r"(?:바깥\s*지름|외경)"),
    "shank_length": ("축부 길이", "mm", r"축부(?:\s*길이)?"),
}
LOAD_FIELDS = {
    "tightening_torque": ("조임 토크", "N·m", r"(?:조임\s*)?토크"),
    "axial_load_max": ("축방향 하중", "N", r"축\s*(?:방향)?\s*하중"),
    "transverse_load": ("축직각 하중", "N", r"(?:축\s*직각|전단|횡)\s*하중"),
    "friction_interface": ("판 사이 마찰계수", "", r"판\s*사이\s*마찰(?:계수)?"),
    "embedding": ("함몰량", "mm", r"함몰(?:량)?"),
}
LABELS = {"size": ("규격", ""), "property_class": ("강도 등급", ""), "friction": ("나사면·좌면 마찰계수", ""),
          "friction_range": ("마찰 범위", ""), "plate_thickness": ("판 두께 (양쪽)", "mm"),
          **{k: v[:2] for k, v in {**JOINT_FIELDS, **LOAD_FIELDS}.items()}}
REPORT = (("preload", "조립 체결력", "N"), ("bolt_equivalent_stress_working", "운전 시 볼트 등가응력", "MPa"), ("safety_yield", "항복 안전율", ""),
          ("safety_opening", "벌어짐 안전율", ""), ("safety_slip", "미끄럼 안전율", ""), ("surface_pressure", "좌면 최대 압력", "MPa"),
          ("safety_fatigue", "피로 안전율", ""))
# 목표를 가리키는 말 → 안전율 키
TARGET_WORDS = {"항복": ("safety_yield",), "벌어짐": ("safety_opening",), "미끄럼": ("safety_slip",), "슬립": ("safety_slip",),
                "면압": ("safety_pressure_head", "safety_pressure_nut"), "피로": ("safety_fatigue",)}

SYSTEM_PROMPT = (
    "너는 볼트 조인트의 설계 값을 바꾸려는 사용자의 말을 읽는다. 바꿀 항목만 JSON 객체 하나로 답한다. 설명을 붙이지 않는다.\n"
    "쓸 수 있는 키: size(예 \"M12\"), property_class(예 \"10.9\"), tightening_torque(N·m), friction(나사면·좌면 마찰계수), "
    "friction_range([최소, 최대]), plate_thickness(양쪽 판 mm), plate_head_thickness, plate_nut_thickness, outer_diameter(mm), "
    "shank_length(mm), axial_load_max(N), transverse_load(N), friction_interface, embedding(mm).\n"
    "사용자가 값을 정하지 않고 목표를 말하면(예: 항복 안전율 1.5 이상이 되게) targets 키 하나만 쓴다: "
    "{\"targets\": {\"safety_yield\": 1.5}}. 목표 키: safety_yield, safety_opening, safety_slip, safety_pressure_head, safety_pressure_nut, safety_fatigue.\n"
    "사용자가 추천 가운데 하나를 고르면(예: 2번으로) {\"choose\": 2} 를 답한다.\n"
    "kN은 N으로 바꾼다. 바꿀 것이 없으면 {} 를 답한다. 계산 결과를 만들지 않는다."
)


@dataclass(frozen=True)
class Turn:
    text: str                           # 사용자의 말
    reply: str                          # 자세한 답 (글)
    source: str                         # "rule" | "llm"
    changes: dict[str, Any]             # 실제로 적용한 변경
    before: PhysicsAnswer
    after: PhysicsAnswer
    note: str = ""
    kind: str = "changed"               # changed | offer | failed | none
    offers: tuple[Candidate, ...] = ()  # kind == "offer"일 때의 추천


def parse_targets(text: str) -> dict[str, float]:
    """"항복 안전율 1.5 이상이 되게"처럼 목표를 말한 부분을 읽는다. 숫자 뒤에 '이상' 같은 말이 있어야 목표로 본다."""
    out: dict[str, float] = {}
    for word, keys in TARGET_WORDS.items():
        m = re.search(rf"{word}(?:\s*안전율)?\s*(?:을|를|이|가|은|는|도)?\s*{NUM}\s*(?:이상|넘게|보다\s*크게|은\s*되게|이\s*되게|가\s*되게|되게|확보)", text)
        if m:
            for k in keys:
                out[k] = float(m.group(1))
    if not out:
        m = re.search(rf"안전율(?:을|를|이|가|은|는)?\s*(?:모두\s*)?{NUM}\s*(?:이상|넘게|되게|확보)", text)
        if m:
            out["safety_yield"] = float(m.group(1))
    return out


def parse_choice(text: str) -> int | None:
    """"2번으로", "1안 적용"처럼 추천 가운데 하나를 고르는 말."""
    m = re.search(r"(\d)\s*(?:번|안)(?:\s*(?:으로|로|적용|선택|해|할게))?", text)
    return int(m.group(1)) if m else None


def _scaled(value: str, unit: str | None) -> float:
    return float(value) * (1000.0 if unit and unit.lower() == "kn" else 1.0)


def parse(text: str) -> dict[str, Any]:
    """말에서 바꿀 항목을 규칙으로 읽는다."""
    out: dict[str, Any] = {}
    m = re.search(r"(?<![A-Za-z])M\s?(\d+)(?!\d)", text)
    if m:
        out["size"] = f"M{m.group(1)}"
    m = re.search(r"(?<![\d.])(\d{1,2}\.\d)(?![\d.])\s*(?:등급|급)|(?:강도\s*등급|등급)\s*(\d{1,2}\.\d)", text)
    if m:
        out["property_class"] = m.group(1) or m.group(2)
    m = re.search(rf"마찰(?:계수)?\s*(?:범위)?\s*(?:를|을|는|은)?\s*{NUM}\s*(?:~|-|에서)\s*{NUM}", text)
    if m:
        out["friction_range"] = [float(m.group(1)), float(m.group(2))]
    rest = text
    for key, (_, _, pat) in {**JOINT_FIELDS, **LOAD_FIELDS}.items():
        m = re.search(rf"{pat}\s*(?:를|을|는|은|이|가)?\s*{NUM}\s*(kN|N·m|Nm|N|mm)?", rest, re.I)
        if m:
            out[key] = _scaled(m.group(1), m.group(2))
            rest = rest[:m.start()] + " " + rest[m.end():]
    m = re.search(rf"판\s*두께\s*(?:를|을|는|은)?\s*{NUM}", rest)
    if m:
        out["plate_thickness"] = float(m.group(1))
    if "friction_range" not in out and "friction_interface" not in out:
        m = re.search(rf"마찰(?:계수)?\s*(?:를|을|는|은)?\s*{NUM}", rest)
        if m:
            out["friction"] = float(m.group(1))
    return out


def _validate(raw: Any) -> dict[str, Any]:
    """LLM이 준 변경을 허용한 항목·형식만 남긴다. 하나라도 어긋나면 ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("not an object")
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k == "targets":
            if not isinstance(v, dict) or not v or any(t not in TARGETS or isinstance(x, bool) or not isinstance(x, (int, float)) for t, x in v.items()):
                raise ValueError("bad targets")
            out[k] = {t: float(x) for t, x in v.items()}
            continue
        if k == "choose":
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError("choose must be an integer")
            out[k] = v
            continue
        if k not in LABELS:
            raise ValueError(f"unknown key {k}")
        if k in ("size", "property_class"):
            out[k] = str(v)
        elif k == "friction_range":
            if not (isinstance(v, list) and len(v) == 2):
                raise ValueError("friction_range must be [min, max]")
            out[k] = [float(v[0]), float(v[1])]
        else:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{k} must be a number")
            out[k] = float(v)
    return out


def apply(joint: BoltedJoint, load: LoadCase, changes: dict[str, Any]) -> tuple[BoltedJoint, LoadCase]:
    """변경을 적용한 새 조인트와 하중. 값이 맞지 않으면 ValueError (원래 것은 그대로다)."""
    c = dict(changes)
    jc: dict[str, Any] = {}; lc: dict[str, Any] = {}
    if "size" in c:
        size = str(c.pop("size")).strip().upper()
        if size not in standards.thread_sizes():
            raise ValueError(f"{size}은(는) 표준 데이터에 없는 규격입니다. 쓸 수 있는 규격: {', '.join(standards.thread_sizes())}")
        jc["size"] = size
    if "property_class" in c:
        cls = str(c.pop("property_class"))
        if cls not in standards.property_classes():
            raise ValueError(f"{cls}은(는) 표준 데이터에 없는 강도 등급입니다. 쓸 수 있는 등급: {', '.join(standards.property_classes())}")
        jc["property_class"] = cls
    if "plate_thickness" in c:
        t = c.pop("plate_thickness"); jc["plate_head_thickness"] = t; jc["plate_nut_thickness"] = t
    if "friction" in c:
        mu = c.pop("friction"); lc["friction_thread"] = mu; lc["friction_head"] = mu
    if "friction_range" in c:
        lc["friction_range"] = tuple(c.pop("friction_range"))
    for k, v in c.items():
        (jc if k in JOINT_FIELDS else lc)[k] = v
    new_load = replace(load, **lc) if lc else load
    if "axial_load_max" in lc and new_load.axial_load_min > new_load.axial_load_max:
        new_load = replace(new_load, axial_load_min=0.0)
    return (joint.modified(**jc) if jc else joint), new_load


def _fmt(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return "~".join(_fmt(x) for x in v)
    return f"{v:g}" if isinstance(v, float) else str(v)


def _current(joint: BoltedJoint, load: LoadCase, key: str) -> Any:
    return {"size": joint.size, "property_class": joint.property_class, "friction": load.friction_thread,
            "friction_range": load.friction_range or "없음", "plate_thickness": joint.plate_head.thickness,
            "plate_head_thickness": joint.plate_head.thickness, "plate_nut_thickness": joint.plate_nut.thickness,
            "outer_diameter": joint.outer_diameter, "shank_length": joint.shank_length}.get(key, getattr(load, key, None))


def _report(before: PhysicsAnswer, after: PhysicsAnswer) -> list[str]:
    lines = []
    for key, label, unit in REPORT:
        a, b = before.value(key), after.value(key)
        if b is None:
            continue
        u = f" {unit}" if unit else ""
        fmt = (lambda v: f"{v:,.0f}") if unit in ("N", "MPa") else (lambda v: f"{v:.2f}")
        lines.append(f"  · {label}: {fmt(b)}{u}" if a is None or fmt(a) == fmt(b) else f"  · {label}: {fmt(a)} → {fmt(b)}{u}")
    return lines


class Session:
    """조인트 하나를 두고 이어 가는 대화. 바꾼 결과가 다음 말의 출발점이 된다."""

    def __init__(self, joint: BoltedJoint, load: LoadCase, provider: Any | None = None):
        self.joint, self.load, self.provider = joint, load, provider
        self.answer = solve(joint, load)
        self.turns: list[Turn] = []
        self.offers: tuple[Candidate, ...] = ()         # 마지막 추천. "2번으로"라고 하면 여기서 고른다

    def _read(self, text: str) -> tuple[dict[str, Any], str, str]:
        def by_rule() -> dict[str, Any]:
            targets = parse_targets(text)
            if targets:
                return {"targets": targets}
            changes = parse(text)
            choice = parse_choice(text)
            return {"choose": choice} if choice is not None and (self.offers or not changes) else changes

        if self.provider is None:
            return by_rule(), "rule", ""
        try:
            r = self.provider.complete([Message("system", SYSTEM_PROMPT), Message("user", text)])
            m = re.search(r"\{.*\}", r.text or "", re.S)
            return _validate(json.loads(m.group(0) if m else "")), "llm", ""
        except Exception as exc:
            return by_rule(), "rule", f"LLM의 답을 쓸 수 없어 규칙으로 읽음 ({type(exc).__name__})"

    def _recommend(self, targets: dict[str, float]) -> str:
        try:
            rec = recommend(self.joint, self.load, targets)
        except ValueError as exc:
            self.offers = ()
            return f"추천을 만들지 못했습니다.\n이유: {exc}"
        self.offers = rec.candidates
        goal = ", ".join(f"{TARGETS[k]} {v:g} 이상" for k, v in targets.items())
        if not rec.candidates:
            return (f"목표({goal})를 만족하는 조합을 찾지 못했습니다.\n표준 데이터에 있는 규격과 강도 등급으로는 어떤 조임 토크에서도 함께 만족하지 못합니다. "
                    "목표를 낮추거나 하중, 마찰, 판 조건을 바꿔 보세요.")
        names = {"size": "규격", "property_class": "강도 등급", "tightening_torque": "조임 토크"}
        lines = [f"목표: {goal}", "지금 설계는 이미 목표를 만족합니다." if rec.current_ok else "지금 설계는 목표에 못 미칩니다.",
                 f"목표를 만족하는 조합은 {rec.total}개이고, 지금 설계에서 가장 적게 바꾸는 순서로 {len(rec.candidates)}개를 보입니다."]
        for i, c in enumerate(rec.candidates):
            what = ", ".join(f"{names[k]} {_fmt(float(v)) if k == 'tightening_torque' else v}{' N·m' if k == 'tightening_torque' else ''}"
                             for k, v in c.changes.items()) or "지금 그대로"
            after = solve(c.joint, c.load)
            safeties = ", ".join(f"{label.replace(' 안전율', '')} {after.value(key):.2f}" for key, label, _ in REPORT
                                 if key.startswith("safety_") and after.value(key) is not None)
            lines.append(f"  {i + 1}번: {what}\n      안전율: {safeties} · 가능한 토크 {torque_span(c)}")
        lines.append("순서는 바꾸는 양이 적은 것부터입니다. 비용이나 무게로 고른 순서가 아닙니다. 적용하려면 \"1번으로\"처럼 말해 주세요.")
        return "\n".join(lines)

    def say(self, text: str) -> Turn:
        changes, source, note = self._read(text)
        before = self.answer
        if "targets" in changes:
            reply = self._recommend(changes["targets"])
            turn = Turn(text, reply, source, {}, before, before, note, "offer" if self.offers else "failed", self.offers)
            self.turns.append(turn)
            return turn
        if "choose" in changes:
            n = changes["choose"]
            if not 1 <= n <= len(self.offers):
                reply = (f"{n}번 추천이 없습니다. " + (f"1~{len(self.offers)}번 가운데 골라 주세요." if self.offers else "먼저 목표를 말해 추천을 받아 주세요."))
                turn = Turn(text, reply, source, {}, before, before, note, "failed")
                self.turns.append(turn)
                return turn
            changes = dict(self.offers[n - 1].changes)
            if not changes:
                turn = Turn(text, f"{n}번은 지금 설계 그대로입니다. 바꾼 것이 없습니다.", source, {}, before, before, note, "none")
                self.turns.append(turn)
                return turn
        if not changes:
            reply = ("바꿀 값을 찾지 못했습니다. 조인트는 그대로입니다.\n예: \"M12로 바꿔\", \"토크 80으로\", \"머리 쪽 판 두께 20\", "
                     "\"마찰 0.10~0.14\", \"축방향 하중 8 kN\", \"강도 등급 8.8\"")
            turn = Turn(text, reply, source, {}, before, before, note, "none")
        else:
            try:
                olds = {k: _current(self.joint, self.load, k) for k in changes}
                joint, load = apply(self.joint, self.load, changes)
                after = solve(joint, load)
            except (ValueError, TypeError) as exc:
                turn = Turn(text, f"바꾸지 못했습니다. 조인트는 그대로입니다.\n이유: {exc}", source, {}, before, before, note, "failed")
            else:
                self.joint, self.load, self.answer = joint, load, after
                self.offers = ()                         # 설계가 바뀌었으니 앞의 추천은 더 쓰지 않는다
                head = ["바꿨습니다."] + [f"  · {LABELS[k][0]}: {_fmt(olds[k])} → {_fmt(v)}{(' ' + LABELS[k][1]) if LABELS[k][1] else ''}"
                                        for k, v in changes.items()]
                if "size" in changes:
                    head.append("  · 규격을 바꾸면 피치와 구멍 지름은 표준값으로 돌아갑니다.")
                turn = Turn(text, "\n".join(head + ["다시 계산한 결과입니다."] + _report(before, after)), source, changes, before, after, note)
        self.turns.append(turn)
        return turn


EXAMPLES = ("토크 60으로", "M12로 바꿔", "축방향 하중 12 kN", "항복 안전율 1.5 이상이 되게")


def brief(turn: Turn) -> dict[str, Any]:
    """한눈에 읽는 답: 한 줄 결론, 가장 크게 달라진 값 몇 개, 눈여겨볼 것 하나. 화면이 이것을 보인다 (자세한 글은 turn.reply)."""
    out: dict[str, Any] = {"kind": turn.kind, "said": turn.text, "headline": "", "chips": [], "alert": "", "alert_low": False,
                           "options": [], "examples": []}
    if turn.kind == "changed":
        what = [f"{LABELS[k][0]} {_fmt(v)}{(' ' + LABELS[k][1]) if LABELS[k][1] else ''}" for k, v in turn.changes.items()]
        out["headline"] = "바꿨습니다: " + ", ".join(what)
        chips = []
        for key, label, unit in REPORT:
            a, b = turn.before.value(key), turn.after.value(key)
            if a is None or b is None:
                continue
            digits = 0 if unit in ("N", "MPa") else 2
            if round(a, digits) == round(b, digits):
                continue
            chips.append({"label": label, "from": round(a, digits), "to": round(b, digits), "unit": unit, "digits": digits,
                          "dir": "up" if b > a else "down", "size": abs(b - a) / max(abs(a), 1e-9), "spot": False,
                          "crossed": key.startswith("safety_") and (a >= 1.0) != (b >= 1.0)})
        chips.sort(key=lambda c: (not c["crossed"], -c["size"]))
        chips = chips[:4]
        if chips:
            chips[0]["spot"] = True
            c = chips[0]
            if c["crossed"]:
                out["alert"] = f"{c['label']}이 1.0 {'아래로 내려갔습니다' if c['to'] < 1.0 else '위로 올라왔습니다'}."
                out["alert_low"] = c["to"] < 1.0
        else:
            out["headline"] += " (계산 결과는 그대로입니다)"
        out["chips"] = [{k: v for k, v in c.items() if k not in ("size", "crossed")} for c in chips]
    elif turn.kind == "offer":
        names = {"size": "", "property_class": "등급 ", "tightening_torque": "토크 "}
        already = bool(turn.offers) and not turn.offers[0].changes
        out["headline"] = ("지금 설계가 이미 목표에 맞습니다. 다른 방법도 볼 수 있습니다." if already
                           else f"목표에 맞는 방법 {len(turn.offers)}가지입니다. 하나를 고르면 적용합니다.")
        for i, c in enumerate(turn.offers):
            what = ", ".join(f"{names[k]}{_fmt(float(v)) + ' N·m' if k == 'tightening_torque' else v}" for k, v in c.changes.items()) or "지금 그대로"
            detail = " · ".join(f"{TARGETS[k].replace(' 안전율', '')} {v:.2f}" for k, v in c.values.items())
            out["options"].append({"n": i + 1, "what": what, "detail": detail, "say": f"{i + 1}번으로"})
    elif turn.kind == "failed":
        lines = turn.reply.split("\n")
        reason = next((ln.replace("이유: ", "") for ln in lines if ln.startswith("이유: ")), "")
        out["headline"] = lines[0] if not reason else "바꾸지 못했습니다."
        out["alert"] = reason or (lines[1] if len(lines) > 1 else "")
        out["alert_low"] = True
    else:
        out["headline"] = turn.reply.split("\n")[0]
        out["examples"] = list(EXAMPLES)
    return out
