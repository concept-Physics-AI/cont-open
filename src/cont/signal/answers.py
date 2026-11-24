"""신호 분석 결과를 공통 결과 형식(PhysicsAnswer)으로 낸다.

신호 분석은 물리 가정이 없는 수학 계산이라 불확실성과 적용 범위를 계산 방법에서 바로 적을 수 있다.
올린 파일(내 신호)은 "관측"으로, 성분을 알고 만든 가상 신호는 "해석"으로 낸다. 어느 쪽도 현장 실측과 대조하지 않았으므로 검증 전이다.
채우지 못한 항목(물리잔차)은 비워 두고 trust()가 "보고하지 않음"이라고 적는다.
"""
from __future__ import annotations

import math
from typing import Sequence

from cont.answer import Confidence, PhysicsAnswer, Quantity, STATUS_OBSERVED, STATUS_SIMULATED
from cont.signal.analysis import Distribution, Spectrogram, Spectrum

_CONF = Confidence("medium", "알려진 신호를 넣어 성분과 분포를 맞게 읽는지 시험했다 (tests/test_signal.py). 이 파일이 가리키는 현장 대상과의 실측 대조는 하지 않았다")


def _status(observed: bool) -> str:
    return STATUS_OBSERVED if observed else STATUS_SIMULATED


def spectrum_answer(sp: Spectrum, top: Sequence[tuple[float, float]], unit: str, source: str, observed: bool, inputs: dict) -> PhysicsAnswer:
    q: list[Quantity] = []
    for i, (f, a) in enumerate(sorted(top), 1):
        q.append(Quantity(f"peak{i}_freq", f"성분 {i}의 주파수", f, "Hz", note=f"간격 {sp.resolution:.3g} Hz 안의 값은 세 점 보간으로 다듬었다"))
        q.append(Quantity(f"peak{i}_amp", f"{f:.4g} Hz 성분의 진폭", a, unit))
    q.append(Quantity("resolution", "주파수 간격", sp.resolution, "Hz"))
    return PhysicsAnswer(
        question="이 신호는 어떤 주파수 성분으로 이루어져 있는가",
        quantities=tuple(q),
        method="푸리에 변환 (한(Hann) 창, 한쪽 진폭). 물리 가정이 없는 수학 계산",
        basis=("가정: 샘플 간격이 일정하다", "봉우리 주파수는 세 점을 지나는 포물선의 꼭짓점으로 다듬음", "직류 성분은 기본으로 뺌"),
        confidence=_CONF,
        inputs=inputs,
        status=_status(observed),
        source=source,
        uncertainty=f"주파수는 간격 {sp.resolution:.3g} Hz 단위로 가려진다 (보간으로 그 안을 다듬되 보증하지 않음). 진폭의 불확실성은 계산하지 않았다",
        scope=f"샘플링 주파수 {sp.fs:.6g} Hz의 절반(나이퀴스트 주파수) 아래만 해석한다. 정상 상태에 가까운 한 구간의 평균 성분",
        failure_conditions=("샘플 간격이 불규칙하면 성분이 번진다", "나이퀴스트 주파수 위의 성분은 낮은 주파수로 접혀 보인다",
                            "단위나 센서 보정이 틀리면 진폭도 틀린다", "신호 중간에 성분이 바뀌면 평균으로 뭉개진다 (시간별 주파수 변화를 본다)"),
    )


def spectrogram_answer(sg: Spectrogram, track: Sequence[float], window: int, source: str, observed: bool, inputs: dict) -> PhysicsAnswer:
    res = sg.fs / window
    q = (Quantity("first_dominant", "처음 구간의 가장 큰 성분", float(track[0]), "Hz"),
         Quantity("last_dominant", "마지막 구간의 가장 큰 성분", float(track[-1]), "Hz"),
         Quantity("resolution", "주파수 간격", res, "Hz"),
         Quantity("window_ms", "조각 길이", window / sg.fs * 1000, "ms"),
         Quantity("segments", "구간 수", float(sg.time.size), "개"))
    return PhysicsAnswer(
        question="시간이 지나면서 주파수 성분이 어떻게 바뀌는가",
        quantities=q,
        method="짧은 구간 푸리에 변환 (한 창, 겹침 포함). 물리 가정이 없는 수학 계산",
        basis=("가정: 샘플 간격이 일정하다", "조각이 짧을수록 시간은 또렷하고 주파수는 흐려진다"),
        confidence=_CONF,
        inputs=inputs,
        status=_status(observed),
        source=source,
        uncertainty=f"주파수는 간격 {res:.3g} Hz, 시간은 조각 길이 {window / sg.fs * 1000:.3g} ms 단위로 가려진다. 진폭의 불확실성은 계산하지 않았다",
        scope=f"샘플링 주파수 {sg.fs:.6g} Hz의 절반 아래. 조각 길이보다 빠르게 바뀌는 변화는 보이지 않는다",
        failure_conditions=("샘플 간격이 불규칙하면 성분이 번진다", "단위나 센서 보정이 틀리면 진폭도 틀린다", "조각보다 짧은 충격은 여러 주파수로 퍼져 보인다"),
    )


def distribution_answer(d: Distribution, unit: str, source: str, observed: bool, inputs: dict) -> PhysicsAnswer:
    se = d.std / math.sqrt(d.n)
    q = (Quantity("n", "개수", float(d.n), "개"),
         Quantity("mean", "평균", d.mean, unit), Quantity("std", "표준편차", d.std, unit), Quantity("median", "중앙값", d.median, unit),
         Quantity("q1", "아래 사분위수", d.q1, unit), Quantity("q3", "위 사분위수", d.q3, unit),
         Quantity("outliers", "벗어난 값", float(len(d.outliers)), "개", note="상자 수염(1.5 × 사분위 범위) 밖의 값"))
    return PhysicsAnswer(
        question="반복해서 잰 값은 어떻게 퍼져 있는가",
        quantities=q,
        method="기술통계 (평균, 표준편차, 사분위수, 막대 분포). 물리 가정이 없는 수학 계산",
        basis=("가정: 값들이 같은 조건에서 반복해 잰 것이다", "표준편차는 n-1로 나눈다"),
        confidence=_CONF,
        inputs=inputs,
        status=_status(observed),
        source=source,
        uncertainty=f"평균의 표준오차 {se:.3g} {unit}".rstrip() + ". 표준편차 자체의 불확실성은 계산하지 않았다",
        scope="주어진 값들의 분포. 앞으로 나올 값이 같은 분포를 따른다는 보증은 없다",
        failure_conditions=("조건이 섞인 값이면 분포가 둘로 갈리는 것을 평균 하나로 가린다", "값이 적으면 사분위수와 벗어난 값 판정이 흔들린다", "단위가 섞이면 의미가 없다"),
    )
