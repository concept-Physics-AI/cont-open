"""표현(이미지 명세·3D 장면·4D·그래프)이 공통 대상 명세와 맞는지 검사하고, 고친 뒤 다시 만들 표현을 고른다."""
from __future__ import annotations

from dataclasses import dataclass, field

from .spec import ObjectSpec


@dataclass(frozen=True)
class Representation:
    id: str                          # 표현 ID (예: 'scene3d', 'image_1')
    kind: str                        # image | scene3d | scene4d | graph | text
    spec_version: str                # 만들 때의 명세 version
    refs: tuple[str, ...]            # 가리키는 부품 ID
    names: tuple[tuple[str, str], ...] = ()      # (부품 ID, 표현에 적힌 이름). 비교할 때만 쓴다


@dataclass
class Report:
    rep: str
    missing: list[str] = field(default_factory=list)       # 명세에는 있는데 표현에 없는 부품
    unknown: list[str] = field(default_factory=list)       # 표현에는 있는데 명세에 없는 ID
    renamed: list[tuple[str, str, str]] = field(default_factory=list)   # (ID, 명세의 이름, 표현의 이름)
    stale: bool = False                                    # 다른 version으로 만든 표현

    @property
    def ok(self) -> bool:
        return not (self.missing or self.unknown or self.renamed or self.stale)

    @property
    def needs_review(self) -> bool:
        return not self.ok


def check(spec: ObjectSpec, rep: Representation, expect_all: bool = True) -> Report:
    """expect_all=False면 일부 부품만 보여 주는 표현(예: 한 층의 그래프)이므로 빠진 부품을 문제로 보지 않는다."""
    r = Report(rep.id, stale=rep.spec_version != spec.version)
    known = set(spec.part_ids)
    r.unknown = sorted(set(rep.refs) - known)
    if expect_all:
        r.missing = sorted(known - set(rep.refs))
    for pid, name in rep.names:
        if pid in known and spec.part(pid).part.name != name:
            r.renamed.append((pid, spec.part(pid).part.name, name))
    return r


def affected(old: ObjectSpec, new: ObjectSpec, reps: list[Representation]) -> dict[str, list[str]]:
    """명세를 고쳤을 때 다시 만들어야 하는 표현과 이유. 바뀐 부품을 가리키지 않는 표현은 건드리지 않는다.

    키: 다시 만들 표현 ID, 값: 겹친 부품 ID. 구조가 같으면(카메라·속도만 바뀐 경우) 빈 결과다.
    """
    changed = set(old.changed_parts(new))
    return {r.id: sorted(changed & set(r.refs)) for r in reps if changed & set(r.refs)}
