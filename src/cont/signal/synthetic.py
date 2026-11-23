"""가상 신호. 정답(성분의 주파수와 크기)을 알고 만들어서 엔진이 맞게 읽는지 확인하는 용도다. 현장 성능의 근거로 쓰지 않는다."""
from __future__ import annotations

import numpy as np


def vibration(fs: float = 2000.0, seconds: float = 2.0, rpm: float = 1500.0, seed: int = 0,
              unbalance: float = 1.0, harmonic2: float = 0.3, fault_hz: float = 0.0, fault_amp: float = 0.0, noise: float = 0.05) -> np.ndarray:
    """회전 진동: 회전 주파수 1배 성분(unbalance), 2배 성분(harmonic2), 선택적인 결함 주파수 성분, 잡음. 단위는 mm/s로 본다."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * seconds)) / fs
    f0 = rpm / 60.0
    x = unbalance * np.sin(2 * np.pi * f0 * t) + harmonic2 * np.sin(2 * np.pi * 2 * f0 * t + 0.7)
    if fault_hz and fault_amp:
        x += fault_amp * np.sin(2 * np.pi * fault_hz * t + 1.3)
    return x + rng.normal(0, noise, t.size)


def run_up(fs: float = 2000.0, seconds: float = 4.0, rpm0: float = 600.0, rpm1: float = 2400.0, seed: int = 0, noise: float = 0.05) -> np.ndarray:
    """속도가 일정하게 올라가는 진동: 회전 주파수 성분이 rpm0에서 rpm1까지 움직인다."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * seconds)) / fs
    f0, f1 = rpm0 / 60.0, rpm1 / 60.0
    phase = 2 * np.pi * (f0 * t + 0.5 * (f1 - f0) * t ** 2 / seconds)
    return np.sin(phase) + rng.normal(0, noise, t.size)


def repeat_values(n: int = 200, mean: float = 10.0, std: float = 0.05, seed: int = 0, outliers: int = 0) -> np.ndarray:
    """반복 작업마다 잰 값 (예: 두께 mm). 평균과 산포를 알고 만든다. outliers개는 평균에서 크게 벗어난다."""
    rng = np.random.default_rng(seed)
    v = rng.normal(mean, std, n)
    if outliers:
        v[:outliers] = mean + 6 * std * rng.choice([-1, 1], outliers)
    return v
