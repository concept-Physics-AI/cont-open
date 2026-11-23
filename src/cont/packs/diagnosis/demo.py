"""진단 화면 만들기.

가상 설비(4계통)로 시연: python -m cont.packs.diagnosis.demo --out demo.html
가상 구동계만:        python -m cont.packs.diagnosis.demo --only drive --out demo.html
특화 진단 시연:       python -m cont.packs.diagnosis.demo --special --out special.html
현장 설정 파일로:     python -m cont.packs.diagnosis.demo --site site.yaml --out result.html
CSV로 진단:          python -m cont.packs.diagnosis.demo --normal normal.csv --current now.csv \
                        --signal motor_A=current --signal vib=vibration --condition load_pct=load --time t --out result.html
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from cont.packs.diagnosis import synthetic
from cont.packs.diagnosis.equipment import EquipmentDiagnosis, diagnose_equipment, load_site, read_csv, site_special
from cont.packs.diagnosis.guidance import guide
from cont.packs.diagnosis.trend import trend
from cont.packs.diagnosis.pack import Diagnosis, diagnose
from cont.view import Section, render_diagnosis, render_equipment, render_special


def synthetic_case() -> Diagnosis:
    normal = synthetic.drive(3000, seed=1)
    current = synthetic.drive(2000, seed=2)
    current = synthetic.inject(current, "current", 1200, 1500, 0.9)                 # 전류가 갑자기 오른 구간
    current = synthetic.inject(current, "vibration", 1600, 2000, 0.6, ramp=True)    # 진동이 서서히 커지는 구간
    return diagnose("drive", normal, current,
                    {"current": "current", "vibration": "vibration", "temperature": "temperature"},
                    {"load": "load", "speed": "speed"}, time="t", question="이 구동부가 평소와 다르게 운전하고 있는가?")


def synthetic_equipment() -> EquipmentDiagnosis:
    """가상 설비 한 대: 구동계와 압력·유동계에 이상을 넣고, 열관리계와 사이클은 계통마다 하나씩 다른 상황을 둔다."""
    drv = synthetic.inject(synthetic.drive(2000, seed=2), "current", 1200, 1500, 0.9)           # 전류 급상승
    drv = synthetic.inject(drv, "vibration", 1600, 2000, 0.6, ramp=True)                        # 진동 점증
    pf = synthetic.inject(synthetic.pressure_flow(2000, seed=12), "dp", 900, 2000, 0.5, ramp=True)   # 차압이 서서히 상승
    pf = synthetic.inject(pf, "flow", 1500, 2000, -2.5)                                         # 유량 감소
    th = synthetic.thermal(2000, seed=22)                                                       # 정상
    cy = synthetic.inject(synthetic.cycle(600, seed=32), "cycle_time", 380, 600, 0.35)          # 사이클 지연
    cy = synthetic.inject(cy, "clamp_time", 380, 600, 0.3)
    return diagnose_equipment([
        {"name": "주 구동부", "module": "drive", "normal": synthetic.drive(3000, seed=1), "current": drv, "time": "t",
         "signals": {"current": "current", "vibration": "vibration", "temperature": "temperature"},
         "conditions": {"load": "load", "speed": "speed"}},
        {"name": "유압 공급 라인", "module": "pressure_flow", "normal": synthetic.pressure_flow(3000, seed=11), "current": pf,
         "time": "t", "signals": {"pressure": "pressure", "flow": "flow", "dp": "pressure_drop"},
         "conditions": {"setpoint": "setpoint", "pump": "speed"}},
        {"name": "가열 구역", "module": "thermal", "normal": synthetic.thermal(3000, seed=21), "current": th, "time": "t",
         "signals": {"error": "tracking_error", "heater": "heater_output", "coolant": "coolant_delta"},
         "conditions": {"setpoint": "setpoint", "ambient": "ambient"}},
        {"name": "동작 사이클", "module": "cycle", "normal": synthetic.cycle(900, seed=31), "current": cy, "time": "cycle",
         "signals": {"cycle_time": "cycle_time", "clamp_time": "step_time", "peak": "peak_load", "stop_error": "position_error"},
         "conditions": {"setting": "speed_setting", "load": "load"}},
    ], equipment="가상 설비 1호기", question="이 설비가 평소와 다르게 운전하고 있는가? 어느 계통인가?")


def synthetic_special() -> list[Section]:
    """특화 진단 세 가지를 가상 데이터로: 절삭(해석 규칙), 프레스(스트로크 부하 곡선), 압출(두께 예측)."""
    from cont.packs.diagnosis.special import assess_quality, diagnose_stroke, fit_quality, interpret
    # 절삭: 주축 부하가 서서히 커지다가(마모) 갑자기 떨어진다(파손)
    cut = synthetic.inject(synthetic.drive(2000, seed=42), "current", 500, 1400, 1.0, ramp=True)
    cut = synthetic.inject(cut, "current", 1400, 2000, -1.6)
    eq = diagnose_equipment([{"name": "주축", "module": "drive", "normal": synthetic.drive(3000, seed=41), "current": cut, "time": "t",
                              "signals": {"current": "current", "vibration": "vibration"},
                              "conditions": {"load": "load", "speed": "speed"}}], equipment="가상 절삭 설비")
    it = interpret("cutting", eq, "주축에서 무슨 일이 있었는가?")
    d = eq.systems[0].diagnosis
    s1 = Section("절삭가공: 공구 상태", "공통 진단(구동계)의 변화를 공정 규칙으로 해석", not it.findings,
                 ", ".join(f.label for f in it.findings) or "공정 규칙에 해당하는 변화 없음", it.answer,
                 tuple((r, d.time, d.settings.z_limit) for r in d.signals), "같은 운전조건의 정상 범위", it.findings)
    # 프레스: 150번째 스트로크부터 성형 구간의 부하가 커진다. 최대 부하보다 곡선 모양에서 먼저 드러난다
    pos, normal = synthetic.stroke_curves(300, seed=51)
    _, cur = synthetic.stroke_curves(250, seed=52)
    sd = diagnose_stroke(normal, synthetic.inject_stroke(cur, pos, 150, 0.35, 0.5, 9.0), pos, question="스트로크의 어느 구간이 평소와 다른가?")
    n_bad = int(sd.answer.value("strokes_flagged"))
    s2 = Section("프레스 성형: 스트로크별 가공 부하", "부하 곡선을 위치별 정상 범위와 비교", n_bad == 0,
                 (f"스트로크 {len(sd.flagged)}회 가운데 {n_bad}회가 벗어남: " + ", ".join(dict.fromkeys(n for n, _ in sd.zones))) if n_bad
                 else "모든 스트로크가 정상 범위 안", sd.answer, ((sd.curve, sd.position, sd.settings.z_limit),), "위치별 정상 범위")
    # 압출: 정답(실측 두께)이 있는 데이터로 모델을 만들고, 인취 속도가 느려진 구간의 두께를 예측한다
    model = fit_quality(synthetic.extrusion(2000, seed=61), "thickness", ["screw", "puller", "melt"])
    now = synthetic.extrusion(1500, seed=62)
    now["puller"][900:] -= 4.0; now["thickness"][900:] += 0.08
    qp = assess_quality(model, now, (1.68, 1.82), time="t", measured="thickness", label="필라멘트 두께", unit="mm",
                        question="두께가 규격 안에 있는가?")
    n_out = int(qp.answer.value("out_of_spec_intervals"))
    s3 = Section("연속 압출: 필라멘트 두께 예측", "공정 값으로 두께를 예측해 규격과 비교", n_out == 0,
                 f"규격 이탈 예측 {n_out}건 (첫 시각 {qp.answer.value('first_out_of_spec_time'):g})" if n_out else "예측 두께가 규격 안",
                 qp.answer, ((qp.chart, qp.time, qp.settings.z_limit),), "규격 범위")
    return [s1, s2, s3]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--normal"); ap.add_argument("--current"); ap.add_argument("--module", default="drive")
    ap.add_argument("--signal", action="append", default=[], metavar="열=역할")
    ap.add_argument("--condition", action="append", default=[], metavar="열=역할")
    ap.add_argument("--site", help="현장 설정 파일 (계통별 CSV와 열 이름 연결)")
    ap.add_argument("--special", action="store_true", help="특화 진단 시연 (가상 데이터)")
    ap.add_argument("--only", help="가상 시연을 계통 하나로만 (drive)")
    ap.add_argument("--time"); ap.add_argument("--out", default="diagnosis.html"); ap.add_argument("--title", default="설비 공통 이상진단")
    a = ap.parse_args(argv)
    if a.special:
        secs = synthetic_special()
        Path(a.out).write_text(render_special(secs, subtitle="가상 데이터 시연: 정답을 알고 만든 신호"), encoding="utf-8")
        print(f"written {a.out}: {sum(not s.ok for s in secs)} of {len(secs)} special case(s) with findings")
        return
    if a.site:
        from cont.dialogue.serve import example_answers
        from cont.packs.diagnosis.special import interpret
        name, systems = load_site(a.site)
        eq = diagnose_equipment(systems, name)
        special = site_special(a.site)
        it = interpret(special, eq) if special else None
        g = guide(eq, it)
        Path(a.out).write_text(render_equipment(eq, a.title, f"현장 설정: {Path(a.site).name}",
                                                example_answers(eq, ("이 설비 지금 어떤가요?", "무엇을 점검해야 하나요?"), guidance=g),
                                                findings=it.findings if it else (), guidance=g, trend=trend(eq)), encoding="utf-8")
        print(f"written {a.out}: {int(eq.answer.value('systems_with_anomaly'))} of {len(eq.systems)} system(s) with anomaly")
        return
    if not (a.normal and a.current) and a.only != "drive":
        from cont.dialogue.serve import example_answers   # 화면에 예시 질문의 답을 미리 담는다
        eq = synthetic_equipment(); g = guide(eq)
        Path(a.out).write_text(render_equipment(eq, a.title, "가상 설비 시연: 정답을 알고 만든 신호", example_answers(eq, guidance=g),
                                                guidance=g, trend=trend(eq)), encoding="utf-8")
        print(f"written {a.out}: {int(eq.answer.value('systems_with_anomaly'))} of {len(eq.systems)} system(s) with anomaly")
        return
    if a.normal and a.current:
        d = diagnose(a.module, read_csv(a.normal), read_csv(a.current), dict(s.split("=", 1) for s in a.signal),
                     dict(c.split("=", 1) for c in a.condition), time=a.time)
        sub = f"{Path(a.current).name} (정상 기준: {Path(a.normal).name})"
    else:
        d = synthetic_case(); sub = "가상 구동계 시연: 전류 급상승과 진동 점증을 넣은 신호"
    Path(a.out).write_text(render_diagnosis(d, a.title, sub), encoding="utf-8")
    print(f"written {a.out}: {sum(len(r.intervals) for r in d.signals)} anomaly interval(s)")


if __name__ == "__main__":
    main()
