"""Physics 열 비교 화면: 같은 기준 문제를 해석식, 수치해석(유한차분), PINN으로 풀어 편차를 한 표에 놓는다.

계산은 이 화면을 만들 때 한다 (격자 수렴, PINN 학습). 값은 모두 같은 정의의 편차다: 해석해와의 차이를 x 101점 x 시각 11개에서 잰 RMS와 최대.
편차가 허용되는지는 판정하지 않는다 (허용 오차를 정하지 않았다). torch가 없는 곳에서 만들면 PINN 행은 만들지 않고 없다고 적는다.
기준 문제: u_t = α u_xx, x∈[0,1], 양 끝 0, 초기 sin(πx), 무차원.
"""
from __future__ import annotations

import html
import math
import os
from functools import lru_cache
from typing import Any

import numpy as np

from cont.learn import available, heat1d, load_profile

GRIDS = ((21, 40), (41, 80), (81, 160), (161, 320))     # (절점 수, 시간 단계 수): 격자를 두 배씩
CHART_GRID = 41                                         # 편차 분포 그림에 쓰는 유한차분 격자
NX, NT = 101, 11


def _profile() -> str:
    return os.environ.get("CONT_HEAT_COMPARE_PROFILE", "heat1d_bench")


def _stats(err: np.ndarray) -> tuple[float, float]:
    return float(np.sqrt(np.mean(err ** 2))), float(np.max(np.abs(err)))


@lru_cache(maxsize=2)
def compare_data(profile: str | None = None) -> dict[str, Any]:
    p = heat1d.Heat1DProblem()
    xs, times = np.linspace(0.0, 1.0, NX), np.linspace(0.0, p.horizon, NT)
    gx, gt = np.meshgrid(xs, times)
    exact = p.exact(gx, gt)
    rows: list[dict[str, Any]] = [{"method": "해석식", "kind": "기준(정답)", "setting": "u = exp(−α π² t) sin(π x)", "rms": None, "max": None,
                                   "status": "기준", "evidence": "—", "note": "다른 방법을 재는 기준이다. 편차의 기준이므로 편차를 재지 않는다"}]
    prev = None
    final_dev: dict[str, list[float]] = {}
    for nx, steps in GRIDS:
        field = heat1d.teacher_field(p, xs, times, nx, steps)
        rms, mx = _stats(field - exact)
        order = None if prev is None else math.log2(prev / rms)
        rows.append({"method": "유한차분", "kind": "수치해석", "setting": f"절점 {nx}, 시간 {steps}단계 (크랭크-니콜슨)", "rms": rms, "max": mx,
                     "status": "해석", "evidence": "E1", "note": "격자를 두 배로 할 때 편차가 줄어든 정도: " + (f"차수 {order:.2f}" if order else "처음 격자")})
        prev = rms
        if nx == CHART_GRID:
            final_dev["fd"] = [float(v) for v in (field - exact)[-1]]
    pinn: dict[str, Any] | None = None
    if available():
        cfg = load_profile(profile or _profile())
        t = heat1d.train(p, cfg)
        err = heat1d.predict(t, gx, gt) - exact
        rms, mx = _stats(err)
        pinn = {"fingerprint": t.record.fingerprint(), "seed": cfg.seed, "epochs": cfg.epochs, "profile": profile or _profile()}
        rows.append({"method": "PINN", "kind": "학습한 모형", "setting": f"시드 {cfg.seed}, 은닉층 {list(cfg.hidden)}, 에포크 {cfg.epochs}, 지문 {t.record.fingerprint()}",
                     "rms": rms, "max": mx, "status": "해석(학습한 모형)", "evidence": "E0",
                     "note": "방정식·경계·초기 조건의 잔차로 학습, 측정 데이터 없음. 학습 범위 밖에서는 쓰지 않는다"})
        final_dev["pinn"] = [float(v) for v in err[-1]]
    return {"rows": rows, "xs": [float(v) for v in xs], "final_dev": final_dev, "pinn": pinn, "alpha": p.alpha, "horizon": p.horizon,
            "fd_chart_nx": CHART_GRID}


CSS = """.hc{margin:8px 0;border:1px solid #DDE2E7;border-radius:16px;padding:20px 22px;background:#fff}.hc h2{margin-top:0}
.hc table{border-collapse:collapse;width:100%;font-size:13.5px}.hc td,.hc th{border-top:1px solid #E6EAEE;padding:6px 8px;text-align:left;vertical-align:top}
.hc th{font-weight:600;color:#3B454E;border-top:0}.hc td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.hc .miss{color:#8A5A00;background:#FFF3DC;border-radius:8px;padding:6px 10px;font-size:12.5px;margin:8px 0}.hc figure{margin:16px 0 0}
.hc figcaption{font-size:12.5px;color:#59636D;margin-top:4px}.hc svg{width:100%;height:auto;max-width:640px;display:block}.hc .sub{font-size:13.5px;color:#59636D}"""


def _fmt(v: float | None) -> str:
    return "—" if v is None else f"{v:.2e}"


def _dev_svg(d: dict[str, Any]) -> str:
    """마지막 시각의 편차 분포 (방법 − 해석해). 색만으로 구분하지 않도록 선 모양과 이름을 함께 쓴다."""
    xs = d["xs"]
    series = [("유한차분(절점 %d)" % d["fd_chart_nx"], d["final_dev"].get("fd"), "", "#3B454E"), ("PINN", d["final_dev"].get("pinn"), "6 3", "#0B6B67")]
    series = [s for s in series if s[1] is not None]
    m = max(max(abs(v) for v in s[1]) for s in series) or 1.0
    m *= 1.15
    W, H, L, R, T, B = 640, 260, 60, 14, 14, 42
    X = lambda x: L + x * (W - L - R)
    Y = lambda v: T + (1 - (v + m) / (2 * m)) * (H - T - B)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="마지막 시각의 해석해와의 편차 분포">',
           f'<line x1="{L}" y1="{Y(0):.1f}" x2="{W - R}" y2="{Y(0):.1f}" stroke="#8A949C" stroke-width="1"/>',
           f'<line x1="{L}" y1="{T}" x2="{L}" y2="{H - B}" stroke="#8A949C" stroke-width="1"/>']
    for v in (-m / 1.15, 0.0, m / 1.15):
        out.append(f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="#59636D">{v:.1e}</text>')
    for x in (0.0, 0.5, 1.0):
        out.append(f'<text x="{X(x):.1f}" y="{H - B + 16}" font-size="11" text-anchor="middle" fill="#59636D">{x:g}</text>')
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 6}" font-size="12" text-anchor="middle" fill="#3B454E">위치 x (무차원)</text>')
    for i, (name, ys, dash, color) in enumerate(series):
        pts = " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in zip(xs, ys))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>')
        ly = T + 14 + 16 * i
        out.append(f'<line x1="{W - 190}" y1="{ly}" x2="{W - 160}" y2="{ly}" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>'
                   f'<text x="{W - 154}" y="{ly + 4}" font-size="12" fill="#1B2229">{html.escape(name)}</text>')
    out.append("</svg>")
    return "".join(out)


def render_heat_compare() -> str:
    e = html.escape
    d = compare_data()
    head = "<tr><th>방법</th><th>종류</th><th>설정</th><th>편차 RMS</th><th>편차 최대</th><th>값의 지위</th><th>증거 수준</th><th>비고</th></tr>"
    body = "".join(f"<tr><td>{e(r['method'])}</td><td>{e(r['kind'])}</td><td>{e(r['setting'])}</td><td class=\"n\">{_fmt(r['rms'])}</td>"
                   f"<td class=\"n\">{_fmt(r['max'])}</td><td>{e(r['status'])}</td><td>{e(r['evidence'])}</td><td>{e(r['note'])}</td></tr>" for r in d["rows"])
    missing = "" if d["pinn"] else ('<p class="miss">이 화면을 만든 곳에는 학습 도구(PyTorch)가 없어 PINN 행을 만들지 않았습니다. '
                                    '없는 값을 채워 넣지 않았습니다.</p>')
    chart = (f'<figure>{_dev_svg(d)}<figcaption>마지막 시각(t = {d["horizon"]:g})의 해석해와의 편차 분포. '
             f'0에 가까울수록 해석해와 같습니다. 어느 쪽이 낫다고 판정하지 않고 어디서 벗어나는지만 봅니다.</figcaption></figure>') if d["final_dev"] else ""
    return (f'<section class="hc"><h2>열 작업대: 식, 수치해석, PINN 비교</h2>'
            f'<p class="sub">1차원 열전도 기준 문제 (u<sub>t</sub> = α u<sub>xx</sub>, α = {d["alpha"]:g}, 양 끝 0, 처음 sin(πx), 무차원)를 세 방법으로 풀고 '
            f'해석해와의 편차를 같은 정의로 쟀습니다 (x {NX}점 × 시각 {NT}개의 RMS와 최대). 표는 화면을 만들 때 계산한 값입니다.</p>{missing}'
            f'<table>{head}{body}</table>{chart}'
            f'<p class="sub">편차가 허용되는지는 판정하지 않습니다 (허용 오차를 정하지 않았습니다). 합성 기준 문제이며 실측과 대조하지 않았습니다. '
            f'증거 수준 E1은 기준 계산과 불변식, E0은 물리 증거가 없다는 뜻입니다.</p></section>')
