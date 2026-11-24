"""공통 결과 형식: 물리 답변 묶음 (PhysicsAnswer).

모든 물리 팩은 이 형식 하나로만 결과를 낸다. 화면(C4)과 검증(C6)은 이 묶음만 본다.
항목: 질문 · 물리량(이름, 값, 단위, 예상 범위, 지위) · 값의 지위 · 증거 연결과 식별가능성(추정값) · 계산 방법 · 근거 · 신뢰도 · 불확실성 · 물리잔차 ·
검증 상태 · 적용 범위 · 실패 조건 · 물리장(면에 퍼진 값) · 표현 지시 · 보관 · 출처(내용 해시와 개정 ID는 내용에서 계산).
값의 지위와 믿을 근거의 뜻은 docs/hidden_physics.md에 있다. 값을 내지 않은 항목은 비워 두고, trust()가 "보고하지 않음"이라고 적는다.
형식을 바꾸는 변경은 기능 변경과 섞지 않고 별도 PR로 다룬다 (ARCHITECTURE.md).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any

RETENTION_EPHEMERAL = "ephemeral"  # 보고 나면 사라지는 일회성 (기본)
RETENTION_SAVED = "saved"          # 사용자가 저장을 요청한 경우

# 값의 지위: 이 값을 어떻게 얻었는가. 관측한 값과 복원·계산한 값을 섞어 보이지 않기 위해 값마다 붙인다.
STATUS_INPUT = "input"             # 사람이 넣은 값, 표준 데이터 (센서로 관측한 것이 아님)
STATUS_OBSERVED = "observed"       # 실제로 관측한 값과 그 값에서 바로 낸 통계
STATUS_ESTIMATED = "estimated"     # 관측에서 복원한 숨은 물리 상태
STATUS_SIMULATED = "simulated"     # 모델과 조건으로 계산한 상태
STATUS_PREDICTED = "predicted"     # 아직 오지 않은 시점이나 재지 않은 대상의 상태
STATUS_GENERATED = "generated"     # 생성한 대안·가설 (검증 전 후보)
STATUS_UNSPECIFIED = "unspecified"
STATUS_LABELS = {STATUS_INPUT: "입력", STATUS_OBSERVED: "관측", STATUS_ESTIMATED: "추정", STATUS_SIMULATED: "해석",
                 STATUS_PREDICTED: "예측", STATUS_GENERATED: "생성 후보", STATUS_UNSPECIFIED: "지위 미정"}

VALIDATION_NONE = "unvalidated"    # 기준값·실측과 대조하지 않음 (기본)
VALIDATION_COMPARED = "compared"   # 기준값·실측과 대조해 편차를 보고함 (판정은 허용 오차 프로파일이 있을 때만)
VALIDATION_LABELS = {VALIDATION_NONE: "검증 전", VALIDATION_COMPARED: "기준값과 대조함"}
NOT_REPORTED = "보고하지 않음"

# 식별가능성: 그 관측으로 그 값을 가려낼 수 있는 정도. 점수 하나로 줄이는 식이 정해져 있지 않아 세 단계와 근거 숫자로 낸다 (docs/hidden_physics.md 5절).
IDENT_OK = "identifiable"
IDENT_WEAK = "weak"
IDENT_NONE = "not_identifiable"
IDENT_LABELS = {IDENT_OK: "가려낼 수 있음", IDENT_WEAK: "약함", IDENT_NONE: "가려낼 수 없음"}


@dataclass(frozen=True)
class Quantity:
    key: str                       # 코드에서 쓰는 이름 (영어)
    label: str                     # 화면에 보이는 이름 (한국어)
    value: float | None            # 계산할 수 없으면 None (이유는 note)
    unit: str
    expected_range: tuple[float, float] | None = None  # (하한, 상한)
    note: str | None = None
    status: str | None = None      # 값의 지위. None이면 묶음의 지위를 따른다
    evidence: tuple[str, ...] = () # 추정값일 때: 이 값이 나온 물리량들의 이름 (같은 묶음 안의 key). 증거 연결
    identifiability: str | None = None        # 추정값일 때: 그 증거로 이 값을 가려낼 수 있는 정도 (IDENT_*)
    identifiability_basis: str | None = None  # 그렇게 본 근거 (숫자를 적는다)


@dataclass(frozen=True)
class Residual:
    """물리잔차: 지켜져야 할 물리 법칙(평형, 보존)에서 결과가 벗어난 크기."""
    key: str
    label: str                     # 어떤 법칙의 잔차인지
    value: float | None
    unit: str
    note: str | None = None        # 이 잔차가 말해 주는 것과 말해 주지 않는 것


@dataclass(frozen=True)
class Field:
    """물리장: 면 위에 퍼진 값. 물리 이미지(C4)는 이것을 그린 것이다.

    격자는 직사각형이다. values[j][i]가 (x[i], y[j]) 자리의 값이고, 재료가 없는 자리는 None이다.
    """
    key: str
    label: str
    unit: str
    axes: tuple[str, str]                          # 두 축의 이름 (예: ("반지름 r", "높이 z"))
    axis_unit: str
    x: tuple[float, ...]
    y: tuple[float, ...]
    values: tuple[tuple[float | None, ...], ...]
    status: str | None = None                      # 값의 지위. None이면 묶음의 지위를 따른다
    note: str | None = None

    def __post_init__(self) -> None:
        if len(self.values) != len(self.y) or any(len(row) != len(self.x) for row in self.values):
            raise ValueError(f"field '{self.key}': values must be len(y) rows of len(x) numbers")

    def range(self) -> tuple[float, float] | None:
        """값의 (최소, 최대). 값이 하나도 없으면 None."""
        flat = [v for row in self.values for v in row if v is not None]
        return (min(flat), max(flat)) if flat else None


@dataclass(frozen=True)
class Confidence:
    level: str                     # high | medium | low
    reason: str


@dataclass(frozen=True)
class Provenance:
    """출처: 이 묶음을 누가, 어느 실행에서, 어느 개정을 바탕으로 만들었는가. 내용 해시에는 넣지 않는다."""
    producer: str = ""             # 만든 곳 (예: "pack:fastening")
    run_id: str = ""               # 실행 ID. 서비스 층이 붙인다
    parent_revision: str = ""      # 바탕이 된 개정 (조건을 바꿔 다시 계산한 경우)


# 해시에 넣지 않는 항목: 보이는 방식, 보관 방식, 출처. 결과의 내용만 해시로 알아본다.
_NOT_HASHED = ("presentation", "retention", "provenance")


def _plain(o: Any) -> Any:
    return float(o) if hasattr(o, "item") and not isinstance(o, (list, tuple, dict)) else str(o)


@dataclass(frozen=True)
class PhysicsAnswer:
    question: str
    quantities: tuple[Quantity, ...]
    method: str                    # 지식표 / 해석식 / AI 대리모델 / 정밀 해석 중 무엇을 썼는지
    basis: tuple[str, ...]         # 출처, 사용한 데이터·식, 가정
    confidence: Confidence
    presentation: tuple[str, ...] = ()   # 어떤 화면으로 보여 줄지 (C4가 해석)
    retention: str = RETENTION_EPHEMERAL
    inputs: dict[str, Any] = field(default_factory=dict)  # 다시 계산할 수 있도록 입력을 함께 둔다
    status: str = STATUS_UNSPECIFIED                      # 이 묶음의 값이 갖는 지위 (물리량마다 따로 적으면 그쪽이 우선)
    source: str = ""                                      # 근거 데이터: 무엇에서 출발한 값인가
    uncertainty: str = ""                                 # 불확실성을 어떻게 반영했는가. 비우면 "보고하지 않음"
    residuals: tuple[Residual, ...] = ()                  # 물리잔차. 비우면 "보고하지 않음"
    validation: str = VALIDATION_NONE
    scope: str = ""                                       # 적용 범위
    failure_conditions: tuple[str, ...] = ()              # 이 결과가 맞지 않게 되는 조건
    fields: tuple[Field, ...] = ()                        # 물리장. 팩이 분포를 계산했을 때만 채운다
    provenance: Provenance = field(default_factory=Provenance)  # 출처. 내용 해시에는 넣지 않는다

    def get(self, key: str) -> Quantity:
        for q in self.quantities:
            if q.key == key:
                return q
        raise KeyError(key)

    def value(self, key: str) -> float | None:
        return self.get(key).value

    def __post_init__(self) -> None:
        keys = {q.key for q in self.quantities}
        for q in self.quantities:
            missing = [e for e in q.evidence if e not in keys]
            if missing:
                raise ValueError(f"quantity '{q.key}': evidence {missing} is not in this answer")
            if q.identifiability is not None and q.identifiability not in IDENT_LABELS:
                raise ValueError(f"quantity '{q.key}': identifiability must be one of {sorted(IDENT_LABELS)}")

    def evidence_of(self, key: str) -> tuple[Quantity, ...]:
        """이 값이 나온 물리량들."""
        return tuple(self.get(e) for e in self.get(key).evidence)

    def evidence_lines(self) -> list[str]:
        """추정한 값마다 한 줄: 증거와 식별가능성. 적지 않은 것은 "보고하지 않음"이라고 적는다."""
        lines = []
        for q in self.quantities:
            if (q.status or self.status) != STATUS_ESTIMATED:
                continue
            src = ", ".join(self.get(e).label for e in q.evidence) or NOT_REPORTED
            ident = NOT_REPORTED if q.identifiability is None else IDENT_LABELS[q.identifiability] + (f" ({q.identifiability_basis})" if q.identifiability_basis else "")
            lines.append(f"{q.label} ← {src}. 식별가능성: {ident}")
        return lines

    def status_of(self, key: str) -> str:
        return self.get(key).status or self.status

    def field(self, key: str) -> Field:
        for f in self.fields:
            if f.key == key:
                return f
        raise KeyError(key)

    def field_status(self, key: str) -> str:
        return self.field(key).status or self.status

    def statuses(self) -> tuple[str, ...]:
        """이 묶음에 들어 있는 지위들 (나온 순서대로, 겹치지 않게)."""
        seen: list[str] = []
        for q in self.quantities:
            st = q.status or self.status
            if st not in seen:
                seen.append(st)
        return tuple(seen)

    def content_hash(self) -> str:
        """결과의 내용으로 만든 SHA-256 (16진수 64자). 같은 내용이면 같고, 값이 하나라도 바뀌면 달라진다. 변조 방지가 아니라 같은 결과인지 알아보는 표식이다."""
        body = {k: v for k, v in asdict(self).items() if k not in _NOT_HASHED}
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_plain).encode("utf-8")).hexdigest()

    def revision_id(self) -> str:
        return "rev-" + self.content_hash()[:12]

    def stamped(self, producer: str, run_id: str = "", parent: "PhysicsAnswer | str | None" = None) -> "PhysicsAnswer":
        """출처를 붙인 사본. 내용은 그대로라 개정 ID도 그대로다."""
        pr = parent.revision_id() if isinstance(parent, PhysicsAnswer) else (parent or "")
        return replace(self, provenance=Provenance(producer, run_id, pr))

    def trust(self) -> list[list[str]]:
        """이 결과를 믿어도 되는가. 값을 내지 않은 항목은 생략하지 않고 "보고하지 않음"이라고 적는다."""
        kinds = self.statuses() or (self.status,)
        missing = [STATUS_LABELS[k] for k in (STATUS_OBSERVED, STATUS_ESTIMATED) if k not in kinds]
        assumed = "; ".join(b.replace("가정: ", "") for b in self.basis if b.startswith("가정"))
        residual = "; ".join(f"{r.label} = {r.value:.3g} {r.unit}" + (f". {r.note}" if r.note else "") if r.value is not None
                             else f"{r.label}: {r.note or NOT_REPORTED}" for r in self.residuals)
        return [
            ["값의 지위", ", ".join(STATUS_LABELS[k] for k in kinds) + (f". {'·'.join(missing)}한 값은 없음" if missing else "")],
            ["근거 데이터", self.source or NOT_REPORTED],
            ["사용 모델", self.method],
            ["가정", assumed or "적어 둔 가정 없음"],
            ["증거와 식별가능성", "; ".join(self.evidence_lines()) or "추정한 값 없음"],
            ["불확실성", self.uncertainty or NOT_REPORTED],
            ["물리잔차", residual or NOT_REPORTED],
            ["검증 상태", f"{VALIDATION_LABELS[self.validation]}. {self.confidence.reason}"],
            ["적용 범위", self.scope or NOT_REPORTED],
            ["실패 조건", "; ".join(self.failure_conditions) or NOT_REPORTED],
            ["개정", f"{self.revision_id()}. 만든 곳: {self.provenance.producer or NOT_REPORTED}. 바탕 개정: {self.provenance.parent_revision or '없음'}"],
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
