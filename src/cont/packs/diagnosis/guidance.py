"""원인 후보와 점검 안내: 찾아낸 변화마다 "무엇을 먼저 확인할지"를 정리한다.

공통 진단의 변화는 tables/guidance.yaml, 특화 진단의 해석은 tables/special/<공정>.yaml의 checks에서 가져온다.
원인을 판정하지 않는다. 후보와 확인할 것을 "먼저 시작된 변화부터, 확인하기 쉬운 것부터" 늘어놓을 뿐이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cont.answer import Confidence, PhysicsAnswer, Quantity
from cont.answer import STATUS_OBSERVED
from cont.packs.diagnosis.equipment import EquipmentDiagnosis
from cont.packs.diagnosis.profile import load_guidance

if TYPE_CHECKING:
    from cont.packs.diagnosis.special.interpret import Interpretation


@dataclass(frozen=True)
class Candidate:
    cause: str          # 원인 후보. 특화 진단의 점검 항목처럼 원인을 따로 적지 않은 경우는 빈 문자열
    check: str          # 확인할 것


@dataclass(frozen=True)
class GuideItem:
    system: str
    signal: str
    title: str          # 변화 이름 (특화 해석이 있으면 그 이름)
    kind: str           # "common" | "special"
    start: float        # 처음 나타난 시각 (그 계통의 시간 열 기준)
    order: float        # 진단 구간 안에서의 상대 위치 0~1 (계통 사이의 순서를 정하는 데 쓴다)
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class Guidance:
    answer: PhysicsAnswer
    items: tuple[GuideItem, ...]


def guide(eq: EquipmentDiagnosis, interpretation: "Interpretation | None" = None, question: str = "") -> Guidance:
    table = load_guidance()
    special = {(f.system, f.signal, f.change): f for f in (interpretation.findings if interpretation else ())}
    rules = {r["key"]: r for r in (interpretation.special.rules if interpretation else ())}
    items: list[GuideItem] = []
    for s in eq.systems:
        d = s.diagnosis; n = max(len(d.time) - 1, 1)
        for r in d.signals:
            for direction in ("up", "down"):
                ivs = [iv for iv in r.intervals if iv.direction == direction]
                ct = d.module.change_type(r.role, direction)
                if not ivs or ct is None:
                    continue
                first = ivs[0]
                f = special.get((s.name, r.column, ct.key))
                if f is not None:
                    cands = tuple(Candidate("", c) for c in rules[f.key].get("checks", []))
                    title, kind = f.label, "special"
                else:
                    cands = tuple(Candidate(c["cause"], c["check"]) for c in table.get(d.module.name, {}).get(ct.key, []))
                    title, kind = ct.label.split(" (")[0], "common"
                items.append(GuideItem(s.name, r.column, title, kind, float(d.time[first.start]), first.start / n, cands))
    items.sort(key=lambda i: (i.order, i.kind != "special"))
    basis = ["찾아낸 변화마다 원인 후보와 확인할 것을 지식표에서 가져옴 (공통: tables/guidance.yaml, 특화: tables/special의 checks)",
             "순서는 먼저 시작된 변화부터, 변화 안에서는 확인하기 쉬운 것부터. 확률 순서가 아니며 원인을 판정한 것이 아님"]
    for i, it in enumerate(items):
        steps = " / ".join((f"{c.cause} → {c.check}" if c.cause else c.check) for c in it.candidates) or "지식표에 항목이 없음"
        basis.append(f"{i + 1}. [{it.system}] {it.title} ({it.signal}, {it.start:g}부터): {steps}")
    if not items:
        basis.append("이상 징후가 없어 점검할 항목이 없음")
    quantities = (Quantity("guide_items", "점검 안내 건수", float(len(items)), "건"),
                  Quantity("guide_checks", "확인할 항목 수", float(sum(len(i.candidates) for i in items)), "개"),
                  Quantity("guide_special_items", "특화 해석이 붙은 건수", float(sum(i.kind == "special" for i in items)), "건"))
    answer = PhysicsAnswer(status=STATUS_OBSERVED, 
        question=question, quantities=quantities, method="지식표 (상태 변화 → 원인 후보와 점검 항목)", basis=tuple(basis),
        confidence=Confidence("low", "원인 후보와 점검 항목은 일반적인 설비 지식으로 쓴 출발점이며 현장의 정비 이력으로 검증하지 않았다"),
        presentation=("list:guidance",), inputs={"equipment": eq.equipment, "special": interpretation.special.name if interpretation else None},
    )
    return Guidance(answer, tuple(items))
