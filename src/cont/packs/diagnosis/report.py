"""진단 결과를 세 묶음으로: 관찰 사실(E), 원인 후보(H), 다음 점검(M). ConT Fab 화면이 쓴다.

- 관찰 사실: 진단 팩이 낸 것 그대로다 (어느 신호가 언제부터 얼마나 벗어났는가).
- 원인 후보: 지식표에서 온 후보다. 판정이 아니다. 특화 해석이 있으면 그 해석이 후보다.
- 다음 점검: 지식표의 확인 항목이다. 순서는 지식표의 순서(확인하기 쉬운 것부터)이며 확률 순서가 아니다.
여기서 숫자를 새로 만들지 않는다. 번호(E-01 등)는 이 보고 안에서만 쓰는 이름이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cont.packs.diagnosis.equipment import EquipmentDiagnosis
from cont.packs.diagnosis.guidance import Guidance, guide


@dataclass(frozen=True)
class Tagged:
    tag: str            # "E-01", "H-02", "M-03"
    text: str


@dataclass(frozen=True)
class Card:
    """찾아낸 변화 하나에 대한 세 묶음."""
    system: str
    signal: str         # 현장 열 이름
    label: str          # 신호의 이름 (예: 전류)
    unit: str
    title: str          # 변화 이름 (특화 해석이 있으면 그 이름)
    kind: str           # "common" | "special"
    direction: str      # up | down
    start: float
    end: float
    peak_z: float       # 가장 크게 벗어난 정도 (정상 산포의 배수, 부호 포함)
    observed: Tagged
    candidates: tuple[Tagged, ...]
    checks: tuple[Tagged, ...]


def _josa(word: str, with_final: str, without: str) -> str:
    ch = word[-1:]
    final = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0
    return word + (with_final if final else without)


def report(eq: EquipmentDiagnosis, interpretation: Any | None = None, guidance: Guidance | None = None) -> tuple[Card, ...]:
    g = guidance or guide(eq, interpretation)
    found = {(f.system, f.signal, f.label): f for f in (interpretation.findings if interpretation else ())}
    systems = {s.name: s.diagnosis for s in eq.systems}
    cards: list[Card] = []
    n_h = n_m = 0
    for i, it in enumerate(g.items, 1):
        d = systems[it.system]
        r = next(x for x in d.signals if x.column == it.signal)
        iv = next(v for v in r.intervals if float(d.time[v.start]) == it.start)
        start, end, peak = float(d.time[iv.start]), float(d.time[iv.end]), float(iv.peak_z)
        f = found.get((it.system, it.signal, it.title)) if it.kind == "special" else None
        if f is not None:                       # 특화 해석은 이어진 구간을 하나로 본다
            start, end, peak = float(f.start), float(f.end), float(f.peak_z)
        word = "높았습니다" if iv.direction == "up" else "낮았습니다"
        observed = (f"{it.system}의 {_josa(r.label, '이', '가')} {start:g}부터 {end:g}까지 같은 운전조건의 평소보다 {word}. "
                    f"가장 크게 벗어난 정도는 정상 산포의 {abs(peak):.1f}배입니다.")
        cands: list[Tagged] = []
        if it.kind == "special":
            n_h += 1
            cands.append(Tagged(f"H-{n_h:02d}", it.title + (". " + f.meaning if f is not None and f.meaning else "")))
        else:
            for c in it.candidates:
                if c.cause:
                    n_h += 1
                    cands.append(Tagged(f"H-{n_h:02d}", c.cause))
        checks: list[Tagged] = []
        for c in it.candidates:
            n_m += 1
            checks.append(Tagged(f"M-{n_m:02d}", c.check))
        cards.append(Card(it.system, it.signal, r.label, r.unit, it.title, it.kind, iv.direction, start, end, peak,
                          Tagged(f"E-{i:02d}", observed), tuple(cands), tuple(checks)))
    return tuple(cards)
