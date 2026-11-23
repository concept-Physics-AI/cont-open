"""설비 진단 결과에 대해 묻고 답하기.

원칙
- 숫자와 판정은 진단 팩이 낸 것만 쓴다. LLM은 질문에 맞게 말을 다듬을 뿐이다.
- LLM 없이도 답한다 (규칙으로 만든 답). LLM이 없거나, 응답이 비었거나, 진단 사실에 없는 숫자를 말하면 규칙 답으로 돌아간다.
- 공통 진단은 "무엇이 어떻게 달라졌는지"까지 답한다. 원인을 단정하지 않는다.
- LLM은 cont.llm 어댑터로만 부른다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cont.llm import Message
from cont.packs.diagnosis.equipment import EquipmentDiagnosis, SystemResult

LEVELS = {"low": "낮음", "medium": "중간", "high": "높음"}
WHEN = ("언제", "시점", "시각", "몇 시", "부터")
WHY = ("왜", "원인", "이유", "때문")
CHECK = ("점검", "확인", "조치", "어떻게", "무엇을", "뭘", "해야")
SYSTEM_PROMPT = (
    "너는 제조 설비의 진단 결과를 현장 담당자에게 설명하는 도우미다.\n"
    "- 아래 '진단 사실'에 있는 내용만 사용한다. 숫자를 새로 만들거나 바꾸지 않는다.\n"
    "- 숫자는 진단 사실에 적힌 그 신호, 그 구간과 짝지어 그대로 쓴다. 다른 신호나 다른 구간의 숫자와 섞지 않는다.\n"
    "- 구간과 시각의 값(예: 1205)에는 단위를 붙이지 않는다. 시간 열의 단위를 모른다.\n"
    "- '정상 산포의 몇 배까지'는 가장 크게 벗어난 정도라는 뜻이다. '이상'으로 바꿔 말하지 않는다.\n"
    "- 원인을 단정하지 않고, 원인의 예를 스스로 들지 않는다. 진단 사실에 '원인 후보'가 있으면 후보라고만 말한다. "
    "'가능성이 높다' 같은 확률 표현을 쓰지 않는다. 원인을 물으면 무엇이 어떻게 달라졌는지 말하고, 원인은 점검으로 확인해야 한다고 답한다.\n"
    "- 한국어 존댓말로, 결론부터, 3~6문장으로 답한다. 굵은 글씨나 목록 같은 꾸밈 기호를 쓰지 않는다."
)
# LLM의 답에 이런 표현이 있으면 규칙 답으로 돌아간다 (2026-11-23 실제 모델로 돌려 보고 넣음)
OVERCLAIM = ("가능성이 높", "가능성이 큽", "확률", "틀림없", "확실히", "분명히")
TIME_UNIT = re.compile(r"\d\s?(?:시|분|초)(?![간각작점기])")       # "1205시"처럼 시각 값에 지어낸 단위


@dataclass(frozen=True)
class Reply:
    text: str
    source: str                 # "llm" | "rule"
    systems: tuple[str, ...]    # 답에 쓴 계통 이름
    facts: str                  # 답의 근거로 쓴 진단 사실
    note: str = ""              # 규칙 답으로 돌아간 이유 등


def _josa(word: str, with_final: str, without: str) -> str:
    """받침에 맞는 조사를 붙인다 (은/는, 이/가)."""
    ch = word.rstrip(")")[-1:] if word else ""
    if "가" <= ch <= "힣":
        return word + (with_final if (ord(ch) - 0xAC00) % 28 else without)
    return word + with_final


def focus(question: str, eq: EquipmentDiagnosis) -> list[tuple[SystemResult, set[str]]]:
    """질문이 가리키는 계통과 신호. 가리키는 것이 없으면 모든 계통.

    돌려주는 값: (계통, 질문이 짚은 신호 열 이름들). 신호 집합이 비어 있으면 그 계통의 모든 신호.
    계통 이름(3점), 신호 이름 전체(2점), 계통을 가리키는 말·신호 이름의 끝말(1점)로 점수를 매기고,
    가장 높은 점수의 절반에 못 미치는 계통은 뺀다 ("가열 구역 온도"가 구동부의 '구동부 온도'까지 끌고 오지 않게).
    """
    q = question.replace(" ", ""); ql = question.lower()
    scored: list[tuple[int, SystemResult, set[str]]] = []
    for s in eq.systems:
        mod = s.diagnosis.module
        score = 3 * (s.name.replace(" ", "") in q) + 3 * (mod.title.replace(" ", "") in q) + sum(k in q for k in mod.keywords)
        cols: set[str] = set()
        for r in s.diagnosis.signals:
            if r.label.replace(" ", "") in q or r.column.lower() in ql:
                score += 2; cols.add(r.column)
            elif r.label.split()[-1] in q:
                score += 1; cols.add(r.column)
        if score:
            scored.append((score, s, cols))
    if not scored:
        return [(s, set()) for s in eq.systems]
    top = max(sc for sc, _, _ in scored)
    return [(s, cols) for sc, s, cols in scored if sc * 2 >= top]


def _evidence(s: SystemResult, cols: set[str]) -> list[str]:
    ev = [b for b in s.diagnosis.answer.basis if "→" in b]
    if cols:
        ev = [b for b in ev if any(f"({c})" in b for c in cols)]
    return ev


def _checks(question: str, eq: EquipmentDiagnosis, guidance: Any | None) -> list[str]:
    """질문이 원인이나 점검을 물을 때, 질문이 가리키는 계통·신호의 점검 안내."""
    if guidance is None or not any(w in question for w in WHY + CHECK):
        return []
    picked = {s.name: cols for s, cols in focus(question, eq)}
    out = []
    for it in guidance.items:
        if it.system in picked and (not picked[it.system] or it.signal in picked[it.system]):
            steps = " / ".join((f"{c.cause} → {c.check}" if c.cause else c.check) for c in it.candidates)
            if steps:
                out.append(f"[{it.system}] {it.title}: {steps}")
    return out


def facts(question: str, eq: EquipmentDiagnosis, guidance: Any | None = None) -> tuple[str, tuple[str, ...]]:
    """질문에 해당하는 진단 사실을 글로 정리한다. LLM에 넘기는 것도, 규칙 답의 재료도 이것 하나다."""
    lines = [f"설비: {eq.equipment or '이름 없음'} (계통 {len(eq.systems)}개 가운데 "
             f"{int(eq.answer.value('systems_with_anomaly'))}개에서 이상 징후)"]
    names = []
    for s, cols in focus(question, eq):
        d = s.diagnosis; names.append(s.name)
        ev = _evidence(s, cols)
        first = d.answer.value("first_anomaly_time")
        if ev:
            lines.append(f"- {s.name}({d.module.title}): 이상 징후 있음" + (f", 첫 이상 시각 {first:g}" if first is not None and not cols else ""))
            lines.extend(f"  · {b}" for b in ev)
        elif cols:
            labels = ", ".join(r.label for r in d.signals if r.column in cols)
            lines.append(f"- {s.name}({d.module.title}): {_josa(labels, '은', '는')} 같은 운전조건의 정상 범위 안")
        else:
            lines.append(f"- {s.name}({d.module.title}): 신호 {len(d.signals)}개 모두 같은 운전조건의 정상 범위 안")
    checks = _checks(question, eq, guidance)
    if checks:
        lines.append("원인 후보와 확인할 것 (판정이 아님, 확인하기 쉬운 것부터):")
        lines.extend(f"  · {c}" for c in checks)
    c = eq.answer.confidence
    lines.append(f"신뢰도: {LEVELS.get(c.level, c.level)} ({c.reason})")
    lines.append("한계: 진단은 무엇이 어떻게 달라졌는지까지 답한다. 원인은 후보일 뿐이며 현장 점검으로 확인한다.")
    return "\n".join(lines), tuple(names)


def rule_answer(question: str, eq: EquipmentDiagnosis, guidance: Any | None = None) -> str:
    """LLM 없이 만드는 답. 같은 질문과 같은 진단 결과에는 항상 같은 답이 나온다."""
    picked = [(s, cols, _evidence(s, cols)) for s, cols in focus(question, eq)]
    bad = [(s, ev) for s, _, ev in picked if ev]
    out: list[str] = []
    if bad:
        out.append("이상 징후가 있는 곳은 " + ", ".join(s.name for s, _ in bad) + "입니다.")
        when = any(w in question for w in WHEN)
        for s, ev in bad:
            first = min(float(b.split(" 값이 ")[1].split("~")[0]) for b in ev)
            head = f"[{s.name}]" + (f" 첫 이상 시각은 {first:g}입니다." if when else "")
            out.append(head + "".join("\n  · " + b.split(" → ")[-1].split(" (")[0] + ": " + b.split(" → ")[0] for b in ev))
    for s, cols, ev in picked:
        if ev:
            continue
        if cols:
            labels = ", ".join(r.label for r in s.diagnosis.signals if r.column in cols)
            line = f"{s.name}의 {_josa(labels, '은', '는')} 같은 운전조건의 정상 범위 안에 있습니다."
            if s.changes:
                line += " 다만 이 계통의 다른 신호에는 이상 징후가 있습니다: " + ", ".join(q.label.split(" (")[0] for q in s.changes) + "."
            out.append(line)
        else:
            out.append(f"{_josa(s.name, '은', '는')} 같은 운전조건의 정상 범위 안에서 운전하고 있습니다.")
    checks = _checks(question, eq, guidance) if bad else []
    if checks:
        out.append("원인은 판정하지 않았습니다. 후보와 먼저 확인할 것은 다음과 같습니다 (확인하기 쉬운 것부터)." + "".join("\n  · " + c for c in checks))
    elif any(w in question for w in WHY) and bad:
        out.append("공통 진단은 무엇이 어떻게 달라졌는지까지 답합니다. 원인은 이 변화를 단서로 현장 점검과 특화 진단에서 확인해야 합니다.")
    c = eq.answer.confidence
    out.append(f"신뢰도는 {LEVELS.get(c.level, c.level)}입니다. {c.reason}.")
    return "\n".join(out)


def _numbers(text: str) -> set[str]:
    return {m.replace(",", "").rstrip(".").lstrip("+") for m in re.findall(r"[+-]?\d[\d,]*(?:\.\d+)?", text)}


def ask(question: str, eq: EquipmentDiagnosis, provider: Any | None = None, guidance: Any | None = None, **opts: Any) -> Reply:
    """provider: cont.llm.get_provider()가 준 것. None이면 규칙 답만 쓴다. guidance: guide()의 결과 (원인·점검 질문에 쓴다)."""
    fact_text, names = facts(question, eq, guidance)
    fallback = rule_answer(question, eq, guidance)
    if provider is None:
        return Reply(fallback, "rule", names, fact_text)
    try:
        r = provider.complete([Message("system", SYSTEM_PROMPT),
                               Message("user", f"진단 사실:\n{fact_text}\n\n질문: {question}")], **opts)
        text = (r.text or "").strip()
    except Exception as exc:  # 공급자가 꺼져 있어도 대화는 이어져야 한다
        return Reply(fallback, "rule", names, fact_text, f"LLM을 부르지 못해 규칙 답을 씀 ({type(exc).__name__})")
    if not text:
        return Reply(fallback, "rule", names, fact_text, "LLM 응답이 비어 규칙 답을 씀")
    text = text.replace("**", "").replace("`", "")          # 꾸밈 기호는 지운다
    said = [w for w in OVERCLAIM if w in text and w not in fact_text]
    if said:
        return Reply(fallback, "rule", names, fact_text, f"LLM 응답이 원인을 확률로 말해 규칙 답을 씀: {', '.join(said)}")
    if TIME_UNIT.search(text) and not TIME_UNIT.search(fact_text):
        return Reply(fallback, "rule", names, fact_text, "LLM 응답이 시각 값에 없는 단위를 붙여 규칙 답을 씀")
    allowed = _numbers(fact_text) | _numbers(question)
    extra = sorted(n for n in _numbers(text) if n.lstrip("-") not in {a.lstrip("-") for a in allowed})
    if extra:
        return Reply(fallback, "rule", names, fact_text, f"LLM 응답에 진단 사실에 없는 숫자가 있어 규칙 답을 씀: {', '.join(extra[:5])}")
    return Reply(text, "llm", names, fact_text)
