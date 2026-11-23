"""체결 대화의 말: 풀어 쓴 답, 다음에 할 말의 추천, 화면을 여는 말.

- 답(talk): 바뀐 것을 문장으로 풀어 쓴다. 문장에 들어가는 숫자는 모두 답변 묶음에서 온다. 여기서 숫자를 만들지 않는다.
- 추천(suggest): 지금 상태에서 다음에 할 만한 말을 규칙으로 고른다. 추천 문구 속의 값(안전율 목표 등)은 설정의 예시 값이다.
- 화면을 여는 말(screen_intent): "응력 분포를 보여 줘"처럼 설계를 바꾸지 않고 화면만 바꾸는 말.
LLM을 쓰지 않는다. 규칙만으로 동작한다.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import yaml

from cont.dialogue.fastening_chat import LABELS, Session, Turn, _current, _fmt, brief
from cont.packs.fastening.field import stress_field
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.packs.fastening.sensing import plan as sensing_plan
from cont.tolerance import CONFIG_DIR

SAFETY_NAMES = (("safety_yield", "항복 안전율"), ("safety_opening", "벌어짐 안전율"), ("safety_slip", "미끄럼 안전율"),
                ("safety_pressure_head", "면압 안전율"), ("safety_pressure_nut", "면압 안전율"), ("safety_fatigue", "피로 안전율"))
RAISE = {"tightening_torque", "axial_load_max", "transverse_load"}      # 올리고 내린다고 말하는 항목
ASK_FIELD, ASK_TRUST, ASK_SENSING = "응력 분포를 보여 줘", "이 결과를 믿어도 돼?", "현장에서는 무엇으로 재야 해?"
START = "예제 조인트로 시작해 줘"
# 숫자를 읽었을 때 받침이 있는가 (0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔). 'ㄹ' 받침(일, 칠, 팔)은 "로"를 쓴다
_DIGIT_BATCHIM = {"0": "ㅇ", "1": "ㄹ", "3": "ㅁ", "6": "ㄱ", "7": "ㄹ", "8": "ㄹ"}
_UNIT_BATCHIM = {"N·m": "", "mm": "", "N": "ㄴ", "kN": "ㄴ", "MPa": "ㄹ"}       # 미터, 뉴턴, 파스칼


@lru_cache(maxsize=1)
def settings() -> dict[str, float]:
    with open(CONFIG_DIR / "fastening" / "default.yaml", encoding="utf-8") as f:
        s = (yaml.safe_load(f) or {})["dialogue"]
    return {"suggest_safety_target": float(s["suggest_safety_target"]), "suggest_torque_step": float(s["suggest_torque_step"]),
            "suggest_count": int(s["suggest_count"])}


def _batchim(word: str) -> str:
    """마지막 글자의 받침: 없으면 "", 'ㄹ'이면 "ㄹ", 그 밖이면 "ㅇ"(있음)."""
    ch = word.strip()[-1:] if word.strip() else ""
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
        return "" if jong == 0 else ("ㄹ" if jong == 8 else "ㅇ")
    if ch.isdigit():
        return _DIGIT_BATCHIM.get(ch, "")
    return ""


def josa(word: str, pair: str) -> str:
    """word 뒤에 붙는 조사. pair: "을를" | "은는" | "이가" | "로"."""
    b = _batchim(word)
    if pair == "로":
        return "로" if b in ("", "ㄹ") else "으로"
    return {"을를": "을", "은는": "은", "이가": "이"}[pair] if b else {"을를": "를", "은는": "는", "이가": "가"}[pair]


def _with_unit(value: Any, unit: str) -> tuple[str, str]:
    """(보이는 글, 조사를 정할 때 읽는 말)."""
    text = _fmt(value) + (f" {unit}" if unit else "")
    return text, ("가" if unit in _UNIT_BATCHIM and not _UNIT_BATCHIM[unit] else "산" if _UNIT_BATCHIM.get(unit) == "ㄴ" else
                  "말" if _UNIT_BATCHIM.get(unit) == "ㄹ" else _fmt(value))


def _change_sentence(key: str, old: Any, new: Any) -> str:
    label, unit = LABELS[key]
    shown, read = _with_unit(new, unit)
    verb = "바꿨습니다"
    if key in RAISE and isinstance(old, (int, float)) and isinstance(new, (int, float)) and old != new:
        verb = "올렸습니다" if new > old else "내렸습니다"
    return f"{label}{josa(label, '을를')} {shown}{josa(read, '로')} {verb}."


def talk(turn: Turn) -> dict[str, Any]:
    """한 말에 대한 풀어 쓴 답. text: 본문, alert: 눈여겨볼 한 문장, alert_low: 그 문장이 나쁜 쪽 소식인가."""
    b = brief(turn)
    out = {"text": "", "alert": b["alert"], "alert_low": b["alert_low"]}
    if turn.kind == "changed":
        j0, l0 = BoltedJoint.from_dict(turn.before.inputs["joint"]), LoadCase.from_dict(turn.before.inputs["load"])
        parts = [_change_sentence(k, _current(j0, l0, k), v) for k, v in turn.changes.items()]
        if "size" in turn.changes:
            parts.append("피치와 구멍 지름은 표준값으로 맞췄습니다.")
        stress = turn.after.value("bolt_equivalent_stress_working")
        was = turn.before.value("bolt_equivalent_stress_working")
        j1 = BoltedJoint.from_dict(turn.after.inputs["joint"])
        if stress is not None and stress > j1.yield_strength and not (was is not None and was > j0.yield_strength):
            out["alert"], out["alert_low"] = "볼트 응력이 항복강도를 넘었습니다.", True
            parts.append("이 토크에서는 볼트가 늘어난 채로 남을 수 있습니다." if "tightening_torque" in turn.changes else "")
        elif not b["chips"]:
            parts.append("계산 결과는 그대로입니다.")
        elif not out["alert"]:
            c = b["chips"][0]
            value = f"{c['to']:,.{c['digits']}f}" + (f" {c['unit']}" if c["unit"] else "")
            parts.append(f"{c['label']}{josa(c['label'], '은는')} {value}{josa('가' if c['unit'] in ('N·m', 'mm') else '산' if c['unit'] in ('N', 'kN') else '말' if c['unit'] == 'MPa' else str(c['to']), '이가')} 되었습니다.")
        out["text"] = " ".join(p for p in parts if p)
    elif turn.kind == "offer":
        out["text"] = b["headline"]
    elif turn.kind == "failed":
        out["text"] = b["headline"] + " 조인트는 그대로입니다."
    else:
        out["text"] = "바꿀 값을 찾지 못했습니다. 조인트는 그대로입니다. 아래의 말처럼 해 보세요."
    return out


def lowest_safety(session: Session) -> tuple[str, float] | None:
    values = [(session.answer.value(k), name) for k, name in SAFETY_NAMES if session.answer.value(k) is not None]
    if not values:
        return None
    v, name = min(values)
    return name, v


def suggest(session: Session, last: str = "") -> list[str]:
    """다음에 할 만한 말. 맨 앞이 가장 권하는 말이다. last: 방금 한 말 (같은 말을 다시 권하지 않는다)."""
    s = settings()
    out: list[str] = []
    if session.offers:
        out += [f"{i + 1}번으로" for i in range(min(2, len(session.offers)))]
    low = lowest_safety(session)
    target = f"{s['suggest_safety_target']:g}"
    stress = session.answer.value("bolt_equivalent_stress_working")
    if stress is not None and stress > session.joint.yield_strength and not session.offers:
        out.append(f"항복 안전율 {target} 이상이 되게 해 줘")
    if low and low[1] < 1.0 and not session.offers:
        out.append(f"{low[0]} {target} 이상이 되게 해 줘")
    if not out:
        out.append(f"토크를 {session.load.tightening_torque + s['suggest_torque_step']:g} N·m로 올려 줘")
    out += [ASK_FIELD, ASK_TRUST, ASK_SENSING]
    seen: list[str] = []
    for t in out:
        if t != last and t not in seen:
            seen.append(t)
    return seen[: s["suggest_count"]]


def screen_intent(text: str, session: Session) -> dict[str, Any] | None:
    """설계를 바꾸지 않고 화면만 바꾸는 말이면 {"view" 또는 "open", "talk"}를, 아니면 None을 돌려준다."""
    t = text.strip()
    j, l, a = session.joint, session.load, session.answer
    if re.search(r"응력\s*분포|물리\s*이미지|압력\s*분포", t):
        f = stress_field(j, l)
        return {"view": "field", "open": None, "talk": {"alert": "", "alert_low": False, "text": (
            f"판 안의 응력 분포를 열었습니다. 판 사이 면의 최대 압력은 {f.value('interface_peak_pressure'):,.0f} MPa이고, "
            f"반지름 {f.value('pressed_radius'):.1f} mm까지 눌립니다. 볼트는 풀지 않고 좌면에 고른 압력을 건 계산이며, 실측과 대조하기 전입니다.")}}
    if re.search(r"믿어도|근거|검증|확실", t):
        spread = "마찰의 흩어짐만 반영했습니다." if l.friction_range else "불확실성은 반영하지 않았습니다."
        return {"view": None, "open": "trust", "talk": {"alert": "", "alert_low": False, "text": (
            f"아직 실측과 대조하지 않은 계산값입니다. {spread} 편심 하중이나 열 하중이 있으면 맞지 않습니다. 오른쪽에 근거를 펼쳐 두었습니다.")}}
    if re.search(r"센서|계측|재야|측정", t):
        p = sensing_plan(j, l)
        text = f"이 조인트에서 볼트는 약 {p.elongation * 1000:.0f} µm 늘어납니다. "
        if p.needed_elongation_uncertainty is not None:
            text += (f"토크만으로 조이면 체결력이 ±{p.torque_only_spread * 100:.0f}% 흩어지므로, 늘어남을 {p.needed_elongation_uncertainty * 1000:.1f} µm보다 "
                     "정밀하게 재야 지금보다 나아집니다. ")
        return {"view": None, "open": "sensing", "talk": {"alert": "", "alert_low": False, "text": text + "단계별 센서와 연결을 오른쪽에 펼쳐 두었습니다."}}
    if re.search(r"시작|체결하려고|지금\s*(조인트|설계)", t):
        low = lowest_safety(session)
        tail = f" 가장 낮은 안전율은 {low[1]:.2f}({low[0].replace(' 안전율', '')})입니다." if low else ""
        return {"view": "shape", "open": None, "talk": {"alert": "", "alert_low": False, "text": (
            ("지금 조인트입니다. " if session.turns else "예제 조인트로 시작합니다. ") + f"{j.size}, 강도 등급 {j.property_class}, 판 {j.plate_head.thickness:g} + {j.plate_nut.thickness:g} mm, "
            f"조임 토크 {l.tightening_torque:g} N·m입니다. 조립 체결력은 {a.value('preload'):,.0f} N입니다.{tail} 오른쪽에서 형상을 돌려 볼 수 있습니다.")}}
    return None
