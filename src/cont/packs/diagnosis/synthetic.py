"""가상 구동계 신호. 실제 현장 데이터가 오기 전에 계산과 화면을 시험하는 용도다.

정답을 알고 만든 신호라서 "계산이 맞는지"는 확인할 수 있지만, 현장 성능의 근거로 쓰지 않는다.
"""
from __future__ import annotations

import numpy as np


def drive(n: int = 2000, seed: int = 0, dt: float = 1.0) -> dict[str, np.ndarray]:
    """정상 운전: 부하와 속도가 바뀌고, 전류·진동·온도는 그 조건을 따라 움직인다."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    load = 50 + 30 * np.sin(2 * np.pi * t / (n * dt / 3)) + rng.normal(0, 2, n)       # 적재량 (%)
    speed = np.where((t // (n * dt / 8)) % 2 == 0, 1000.0, 1500.0) + rng.normal(0, 5, n)  # 회전수 (rpm)
    current = 2.0 + 0.08 * load + 0.002 * speed + rng.normal(0, 0.10, n)              # 전류 (A)
    vibration = 0.8 + 0.0012 * speed + 0.004 * load + rng.normal(0, 0.05, n)          # 진동 (mm/s)
    temperature = 35 + 0.15 * load + 0.004 * speed + rng.normal(0, 0.3, n)            # 온도 (°C)
    return {"t": t, "load": load, "speed": speed, "current": current, "vibration": vibration, "temperature": temperature}


def inject(data: dict[str, np.ndarray], signal: str, start: int, end: int, delta: float,
           ramp: bool = False) -> dict[str, np.ndarray]:
    """signal의 [start, end) 구간에 delta만큼의 변화를 넣는다. ramp=True면 서서히 커진다."""
    out = {k: np.array(v, dtype=float, copy=True) for k, v in data.items()}
    shape = np.linspace(0, 1, end - start) if ramp else np.ones(end - start)
    out[signal][start:end] += delta * shape
    return out


def pressure_flow(n: int = 2000, seed: int = 0, dt: float = 1.0) -> dict[str, np.ndarray]:
    """정상 운전: 설정 압력과 펌프 속도가 바뀌고, 압력·유량·차압은 그 조건을 따라 움직인다."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    setpoint = 80 + 20 * np.sin(2 * np.pi * t / (n * dt / 2)) + rng.normal(0, 0.5, n)   # 설정 압력 (bar)
    pump = np.where((t // (n * dt / 6)) % 2 == 0, 1200.0, 1600.0) + rng.normal(0, 4, n)  # 펌프 속도 (rpm)
    pressure = 0.98 * setpoint + 0.001 * pump + rng.normal(0, 0.4, n)                    # 압력 (bar)
    flow = 0.02 * pump + 0.05 * setpoint + rng.normal(0, 0.3, n)                         # 유량 (L/min)
    dp = 0.5 + 0.0015 * pump + 0.004 * setpoint + rng.normal(0, 0.04, n)                 # 필터 차압 (bar)
    return {"t": t, "setpoint": setpoint, "pump": pump, "pressure": pressure, "flow": flow, "dp": dp}


def thermal(n: int = 2000, seed: int = 0, dt: float = 1.0) -> dict[str, np.ndarray]:
    """정상 운전: 설정 온도와 주변 온도가 천천히 바뀐다 (급한 변경에 따른 과도 구간은 넣지 않는다)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    setpoint = 200 + 15 * np.sin(2 * np.pi * t / (n * dt / 2)) + rng.normal(0, 0.1, n)   # 설정 온도 (°C)
    ambient = 24 + 4 * np.sin(2 * np.pi * t / (n * dt)) + rng.normal(0, 0.2, n)          # 주변 온도 (°C)
    temperature = setpoint + rng.normal(0, 0.5, n)                                       # 구역 온도 (°C)
    heater = 10 + 0.3 * (setpoint - ambient) + rng.normal(0, 0.8, n)                     # 히터 출력 (%)
    coolant = 2.0 + 0.012 * setpoint + rng.normal(0, 0.08, n)                            # 냉각수 온도차 (°C)
    return {"t": t, "setpoint": setpoint, "ambient": ambient, "temperature": temperature,
            "error": temperature - setpoint, "heater": heater, "coolant": coolant}


def cycle(n: int = 600, seed: int = 0) -> dict[str, np.ndarray]:
    """정상 운전: 표본 하나가 사이클 한 번. 설정 속도와 처리 부하에 따라 사이클 시간과 최대 부하가 달라진다."""
    rng = np.random.default_rng(seed)
    k = np.arange(n, dtype=float)
    setting = np.where((k // (n / 4)) % 2 == 0, 60.0, 80.0)                              # 설정 속도 (%)
    load = 40 + 15 * np.sin(2 * np.pi * k / (n / 3)) + rng.normal(0, 1.0, n)             # 처리 부하
    cycle_time = 12.0 - 0.06 * setting + 0.01 * load + rng.normal(0, 0.05, n)            # 사이클 시간 (s)
    clamp_time = 2.5 - 0.012 * setting + rng.normal(0, 0.02, n)                          # 한 구간의 동작 시간 (s)
    peak = 20 + 1.1 * load + 0.1 * setting + rng.normal(0, 0.8, n)                       # 사이클 최대 부하
    stop_error = 0.05 + 0.0004 * setting + np.abs(rng.normal(0, 0.006, n))               # 정지 위치 편차 (mm)
    return {"cycle": k, "setting": setting, "load": load, "cycle_time": cycle_time, "clamp_time": clamp_time,
            "peak": peak, "stop_error": stop_error}


def stroke_curves(n: int = 200, points: int = 120, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """프레스 스트로크의 부하 곡선 (위치 0~1, 스트로크 n회). 접촉 뒤 부하가 올라 성형 구간에서 가장 크고 하사점에서 내려온다."""
    rng = np.random.default_rng(seed)
    pos = np.linspace(0.0, 1.0, points)
    shape = 100.0 * np.exp(-((pos - 0.62) / 0.16) ** 2) + 12.0 / (1.0 + np.exp(-(pos - 0.25) / 0.03))
    gain = 1.0 + rng.normal(0, 0.01, (n, 1))                       # 스트로크마다 조금씩 다른 전체 크기
    return pos, shape * gain + rng.normal(0, 1.0, (n, points))


def inject_stroke(curves: np.ndarray, pos: np.ndarray, first: int, lo: float, hi: float, delta: float) -> np.ndarray:
    """first번째 스트로크부터 위치 lo~hi 구간의 부하를 delta만큼 바꾼다."""
    out = np.array(curves, dtype=float, copy=True)
    out[first:, (pos >= lo) & (pos <= hi)] += delta
    return out


def extrusion(n: int = 1500, seed: int = 0, dt: float = 1.0) -> dict[str, np.ndarray]:
    """연속 압출: 스크루 속도, 인취 속도, 용융 온도가 바뀌고 필라멘트 두께는 그 값을 따라 정해진다 (두께가 정답)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    screw = 60 + 4 * np.sin(2 * np.pi * t / (n * dt / 3)) + rng.normal(0, 0.3, n)        # 스크루 속도 (rpm)
    puller = 30 + 1.5 * np.sin(2 * np.pi * t / (n * dt / 5) + 1.0) + rng.normal(0, 0.1, n)  # 인취 속도 (m/min)
    melt = 200 + 3 * np.sin(2 * np.pi * t / (n * dt / 2)) + rng.normal(0, 0.2, n)        # 용융 온도 (°C)
    thickness = 1.75 + 0.006 * (screw - 60) - 0.02 * (puller - 30) - 0.002 * (melt - 200) + rng.normal(0, 0.008, n)  # 두께 (mm)
    return {"t": t, "screw": screw, "puller": puller, "melt": melt, "thickness": thickness}
