"""선택한 부분만 고치기 (P4): 사용자가 가리킨 것을 부품 ID로 풀고, 그 부품만 고친 새 명세와 변경 전후를 돌려준다.

가리키는 방법: 부품 ID, 부품 이름, 층 이름(여러 부품), 옆면 그림 위의 사각형 영역. 모호하거나 못 찾으면
고르지 않고 후보를 알려 준다(추측으로 고치지 않는다). 영역은 **우리가 그린 옆면 단면 도식**(쉬는 자세) 기준이다.
생성한 그림 위의 영역은 그림에 부품 위치 정보가 없으므로 이 방식으로 풀 수 없다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .check import Representation, affected
from .spec import ObjectSpec, ObjectSpecError


class SelectionError(ObjectSpecError):
    """가리킨 것을 하나로 정할 수 없을 때. candidates에 후보가 있다."""

    def __init__(self, message: str, candidates: tuple[str, ...] = ()):
        super().__init__(message)
        self.candidates = candidates


@dataclass(frozen=True)
class Selection:
    parts: tuple[str, ...]
    how: str                      # id | name | layer | region


def select(spec: ObjectSpec, ref: str) -> Selection:
    """ID → 이름(정확히) → 층 → 이름 일부 순서로 찾는다. 부품은 하나로 정해져야 하고, 층은 그 층의 모든 부품이다."""
    if not isinstance(ref, str) or not ref.strip():
        raise SelectionError("무엇을 가리키는지 비어 있습니다")
    ref = ref.strip()
    by = [(p.id, p.part.name, p.layer) for p in spec.parts]
    for pid, _, _ in by:
        if pid == ref:
            return Selection((pid,), "id")
    names = [pid for pid, n, _ in by if n == ref]
    if len(names) == 1:
        return Selection((names[0],), "name")
    if len(names) > 1:
        raise SelectionError(f"이름 '{ref}'인 부품이 {len(names)}개입니다", tuple(names))
    layer = tuple(pid for pid, _, l in by if l == ref)
    if layer:
        return Selection(layer, "layer")
    part = [pid for pid, n, _ in by if ref in n]
    if len(part) == 1:
        return Selection((part[0],), "name")
    if len(part) > 1:
        raise SelectionError(f"'{ref}'가 여러 부품에 해당합니다. 하나를 골라 주세요", tuple(part))
    raise SelectionError(f"'{ref}'에 해당하는 부품이 없습니다", tuple(pid for pid, _, _ in by))


def _boxes(spec: ObjectSpec) -> dict[str, tuple[float, float, float, float]]:
    """옆면 단면 도식의 부품 상자 (x0, y0, x1, y1), 0~1. 가로는 지름, 세로는 z(위가 0). 쉬는 자세 기준."""
    half = max(p.part.outer for p in spec.parts) / 2
    z0 = min(p.part.z0 for p in spec.parts)
    z1 = max(p.part.z1 for p in spec.parts)
    out = {}
    for p in spec.parts:
        o = p.part.outer / 2
        out[p.id] = ((half - o) / (2 * half), (z1 - p.part.z1) / (z1 - z0), (half + o) / (2 * half), (z1 - p.part.z0) / (z1 - z0))
    return out


def select_region(spec: ObjectSpec, rect: tuple[float, float, float, float], min_cover: float = 0.5) -> Selection:
    """옆면 도식 위 사각형(x0, y0, x1, y1, 0~1)이 덮는 부품. 부품 상자의 min_cover 이상을 덮은 부품을 고르고,
    없으면 사각형 중심이 든 부품 하나를 고른다. 그것도 없으면 거절한다."""
    x0, y0, x1, y1 = rect
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise SelectionError("영역은 0~1 범위의 (x0, y0, x1, y1)이고 x0<x1, y0<y1이어야 합니다")
    boxes = _boxes(spec)
    hit = []
    for pid, (a, b, c, d) in boxes.items():
        w, h = min(x1, c) - max(x0, a), min(y1, d) - max(y0, b)
        if w > 0 and h > 0 and w * h >= min_cover * (c - a) * (d - b):
            hit.append(pid)
    if hit:
        return Selection(tuple(hit), "region")
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hit = [pid for pid, (a, b, c, d) in boxes.items() if a <= cx <= c and b <= cy <= d]
    if len(hit) == 1:
        return Selection(tuple(hit), "region")
    raise SelectionError("영역이 부품을 하나로 가리키지 못합니다", tuple(boxes))


@dataclass
class EditResult:
    old: ObjectSpec
    new: ObjectSpec
    selection: Selection
    changed: tuple[str, ...]                      # 값이 실제로 달라진 부품
    unchanged: tuple[str, ...]                    # 그대로인 부품 (선택 밖 + 선택했지만 값이 같은 부품)
    diff: dict[str, dict[str, tuple[Any, Any]]] = field(default_factory=dict)    # 부품 ID → 항목 → (전, 후)

    @property
    def version_changed(self) -> bool:
        return self.old.version != self.new.version

    def rebuild(self, reps: list[Representation]) -> dict[str, list[str]]:
        """다시 만들 표현만. 고친 부품을 가리키지 않는 표현은 포함하지 않는다."""
        return affected(self.old, self.new, reps)


_FIELDS = ("name", "z0", "z1", "outer", "inner")


def edit_selection(spec: ObjectSpec, selection: Selection, **changes: Any) -> EditResult:
    """선택한 부품에만 같은 변경을 적용한다. 선택 밖 부품은 바이트 단위로 그대로다(시험이 확인).

    z0·z1을 여러 부품에 주면 각각 그 값이 된다. 층이 서로 겹치는 변경은 막지 않는다
    (설명용 도식이므로 사용자가 결정하고, 겹침은 `overlaps`로 알려 준다). 이름은 부품 하나에만 줄 수 있다."""
    if not selection.parts:
        raise SelectionError("선택한 부품이 없습니다")
    if "name" in changes and len(selection.parts) > 1:
        raise SelectionError("여러 부품에 같은 이름을 줄 수 없습니다. 이름은 부품 하나씩 고칩니다", selection.parts)
    new = spec
    for pid in selection.parts:
        new = new.edit_part(pid, **changes)
    new = replace(new, parent_version=spec.version)
    changed = spec.changed_parts(new)
    if not changed:
        new = spec                                  # 같은 값으로 고친 것은 고친 것이 아니다 (version·치수 상태 그대로)
    diff: dict[str, dict[str, tuple[Any, Any]]] = {}
    for pid in changed:
        a, b = spec.part(pid).part, new.part(pid).part
        diff[pid] = {f: (getattr(a, f), getattr(b, f)) for f in _FIELDS if getattr(a, f) != getattr(b, f)}
    unchanged = tuple(i for i in spec.part_ids if i not in changed)
    return EditResult(spec, new, selection, changed, unchanged, diff)


def overlaps(spec: ObjectSpec) -> list[tuple[str, str]]:
    """z 방향으로 겹치는 부품 쌍. 고친 뒤 확인용이다."""
    ps = sorted(spec.parts, key=lambda p: p.part.z0)
    return [(a.id, b.id) for i, a in enumerate(ps) for b in ps[i + 1:] if b.part.z0 < a.part.z1 - 1e-9]
