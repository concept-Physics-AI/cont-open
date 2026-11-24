"""CSV(또는 탭·세미콜론으로 나눈 글) 읽기와 샘플링 주파수 구하기.

규칙: 첫 줄에 숫자가 아닌 칸이 하나라도 있으면 열 이름 줄로 본다. 숫자는 소수점이 점(.)인 것만 읽는다.
읽을 수 없는 칸이 있으면 몇 번째 줄 어느 열인지 알려 주고 멈춘다 (빈칸을 조용히 건너뛰지 않는다).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import numpy as np

MAX_ROWS = 1_000_000
DELIMITERS = (",", "\t", ";")


@dataclass(frozen=True)
class Table:
    names: list[str]
    columns: list[np.ndarray]

    @property
    def rows(self) -> int:
        return int(self.columns[0].size) if self.columns else 0


def _num(cell: str) -> float | None:
    cell = cell.strip()
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError:
        return None


def parse_table(text: str) -> Table:
    text = text.lstrip("﻿")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError("줄이 너무 적습니다. 값이 두 줄 이상 있어야 합니다")
    delim = max(DELIMITERS, key=lambda d: lines[0].count(d))      # 동률이면 앞의 것 (쉼표)
    rows = list(csv.reader(lines, delimiter=delim))
    width = len(rows[0])
    header = any(_num(c) is None for c in rows[0])
    names = [c.strip() or f"열 {i + 1}" for i, c in enumerate(rows[0])] if header else [f"열 {i + 1}" for i in range(width)]
    body = rows[1:] if header else rows
    if len(body) > MAX_ROWS:
        raise ValueError(f"줄이 너무 많습니다 ({len(body):,}줄). {MAX_ROWS:,}줄 이하로 줄여 주세요")
    if len(body) < 2:
        raise ValueError("값이 있는 줄이 너무 적습니다")
    data = np.empty((len(body), width))
    for i, r in enumerate(body):
        if len(r) != width:
            raise ValueError(f"{i + 1 + header}번째 줄의 칸 수가 {len(r)}개입니다 (첫 줄은 {width}개)")
        for j, c in enumerate(r):
            v = _num(c)
            if v is None or not np.isfinite(v):
                raise ValueError(f"{i + 1 + header}번째 줄, '{names[j]}' 열의 '{c.strip()[:20]}'을(를) 숫자로 읽지 못했습니다 (소수점은 점으로 적어 주세요)")
            data[i, j] = v
    return Table(names, [data[:, j].copy() for j in range(width)])


def sampling(time: np.ndarray) -> tuple[float, float]:
    """시간 열(초)에서 샘플링 주파수(Hz)와 간격 흔들림(중앙 간격 대비 최대 편차 비율)을 구한다. 시간이 늘어나지 않으면 오류."""
    dt = np.diff(np.asarray(time, dtype=float))
    if dt.size < 1 or np.any(dt <= 0):
        raise ValueError("시간 열이 계속 늘어나지 않습니다. 시간 열을 다시 골라 주세요")
    med = float(np.median(dt))
    return 1.0 / med, float(np.max(np.abs(dt - med)) / med)
