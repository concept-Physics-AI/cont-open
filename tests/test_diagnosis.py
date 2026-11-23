import numpy as np
import pytest

from cont import packs
from cont.packs.diagnosis import baseline, detect, diagnose
from cont.packs.diagnosis import synthetic as syn
from cont.packs.diagnosis.demo import main as demo_main
from cont.packs.diagnosis.demo import synthetic_case
from cont.packs.diagnosis.profile import load_module, load_settings
from cont.view import render_diagnosis

SIG = {"current": "current", "vibration": "vibration", "temperature": "temperature"}
COND = {"load": "load", "speed": "speed"}


def run(current, **kw):
    return diagnose("drive", syn.drive(3000, seed=1), current, kw.pop("signals", SIG), kw.pop("conditions", COND), time="t", **kw)


def test_normal_operation_raises_no_alarm_even_though_load_and_speed_change():
    d = run(syn.drive(2000, seed=3))
    assert sum(len(r.intervals) for r in d.signals) == 0
    assert d.answer.value("anomaly_intervals") == 0 and d.answer.value("first_anomaly_time") is None
    assert all(r.conditioned_fraction == 1.0 for r in d.signals)


def test_condition_change_alone_is_not_an_anomaly_but_a_fixed_limit_would_flag_it():
    cur = syn.drive(2000, seed=4)
    cur["load"] = cur["load"] + 25.0                      # 적재량이 늘어 전류도 함께 오른 정상 운전
    cur["current"] = cur["current"] + 0.08 * 25.0
    d = run(cur, signals={"current": "current"})
    assert len(d.signals[0].intervals) == 0
    normal = syn.drive(3000, seed=1)["current"]
    assert np.mean(cur["current"] > np.quantile(normal, 0.99)) > 0.2   # 조건을 보지 않는 고정 기준이면 오경보


def test_step_in_current_is_found_at_the_injected_place_and_named_load_increase():
    d = run(syn.inject(syn.drive(2000, seed=2), "current", 1200, 1500, 0.9))
    (iv,) = d.signals[0].intervals
    assert (iv.start, iv.end, iv.direction) == (1200, 1499, "up")
    assert d.answer.value("first_anomaly_time") == 1200.0
    assert d.answer.value("change_load_increase") == pytest.approx(iv.peak_z)
    assert any("부하 증가" in b and "1200~1499" in b for b in d.answer.basis)
    assert not d.signals[1].intervals and not d.signals[2].intervals      # 다른 신호는 정상


def test_slow_vibration_growth_is_found_and_drop_in_current_is_named_separately():
    cur = syn.inject(syn.drive(2000, seed=2), "vibration", 1600, 2000, 0.6, ramp=True)
    cur = syn.inject(cur, "current", 300, 400, -1.0)
    d = run(cur)
    vib = d.signals[1].intervals
    assert len(vib) == 1 and vib[0].direction == "up" and 1600 < vib[0].start < 1800 and vib[0].end == 1999
    assert d.answer.value("change_vibration_increase") > load_settings().z_limit
    assert d.answer.value("change_load_decrease") < -load_settings().z_limit


def test_short_spikes_are_ignored_and_nearby_runs_are_merged():
    z = np.zeros(200)
    z[10:13] = 9.0                       # 3표본짜리 튐: min_run=5 미만
    z[50:56] = 6.0; z[58:64] = 6.0       # 2표본 떨어진 두 구간: merge_gap=3 이하라 하나로
    z[120:130] = -7.0
    ivs = detect.intervals(z, "x", z_limit=4.0, min_run=5, merge_gap=3)
    assert [(i.start, i.end, i.direction) for i in ivs] == [(50, 63, "up"), (120, 129, "down")]


def test_baseline_follows_conditions_and_falls_back_when_a_bin_has_few_samples():
    n = syn.drive(3000, seed=1)
    b = baseline.fit(n, ["current"], ["load", "speed"], 4, 30)
    assert b.coef["current"][1] == pytest.approx(0.08, abs=0.005) and b.coef["current"][2] == pytest.approx(0.002, abs=0.0005)
    assert b.global_scale["current"] == pytest.approx(0.10, rel=0.15)
    far = {"load": np.array([50.0]), "speed": np.array([1000.0]), "current": np.array([8.0])}
    sparse = baseline.fit({k: v[:40] for k, v in n.items()}, ["current"], ["load", "speed"], 4, 30)
    _, scale, used = sparse.reference(far, "current")
    assert not used[0] and scale[0] == sparse.global_scale["current"]
    with pytest.raises(ValueError):
        baseline.fit(n, ["no_such_column"], ["load"], 4, 30)


def test_site_columns_are_mapped_to_module_roles():
    normal = syn.drive(3000, seed=1); cur = syn.inject(syn.drive(1000, seed=5), "current", 400, 600, 1.0)
    ren = {"current": "MTR01_A", "load": "LOAD_PCT", "speed": "RPM"}
    n2 = {ren.get(k, k): v for k, v in normal.items()}; c2 = {ren.get(k, k): v for k, v in cur.items()}
    d = diagnose("drive", n2, c2, {"MTR01_A": "current"}, {"LOAD_PCT": "load", "RPM": "speed"}, time="t")
    assert d.signals[0].column == "MTR01_A" and d.signals[0].label == "전류" and len(d.signals[0].intervals) == 1
    with pytest.raises(ValueError):
        diagnose("drive", n2, c2, {"MTR01_A": "pressure"})          # 구동계에 없는 역할
    with pytest.raises(ValueError):
        diagnose("hydraulic", n2, c2, {"MTR01_A": "current"})       # 아직 없는 모듈


def test_settings_come_from_config_profiles(tmp_path, monkeypatch):
    assert load_settings().z_limit == 4.0 and load_module("drive").change_type("current", "up").key == "load_increase"
    d = tmp_path / "diagnosis"; (d / "profiles").mkdir(parents=True)
    (d / "default.yaml").write_text("baseline: {bins_per_condition: 4, min_samples_per_bin: 30}\n"
                                    "detection: {z_limit: 4.0, min_run: 5, merge_gap: 3}\n"
                                    "special: {abrupt_jump_ratio: 0.75, min_training_samples: 50}\ntrend: {windows: 12}\n", encoding="utf-8")
    (d / "profiles" / "strict.yaml").write_text("detection: {z_limit: 2.5}\n", encoding="utf-8")
    s = load_settings("strict", config_dir=tmp_path)
    assert (s.z_limit, s.min_run, s.bins_per_condition) == (2.5, 5, 4)
    with pytest.raises(FileNotFoundError):
        load_settings("nope", config_dir=tmp_path)


def test_pack_gives_the_common_answer_format_and_the_screen_renders(tmp_path):
    cur = syn.inject(syn.drive(2000, seed=2), "current", 1200, 1500, 0.9)
    ans = packs.get("diagnosis").solve({"module": "drive", "normal": syn.drive(3000, seed=1), "current": cur,
                                        "signals": SIG, "conditions": COND, "time": "t"}, question="평소와 다른가?")
    assert {"diagnosis", "fastening"} <= set(packs.names())
    assert ans.method.startswith("통계 기준 비교") and ans.confidence.level == "low" and ans.value("anomaly_intervals") == 1
    assert set(ans.to_dict()) == {"question", "quantities", "method", "basis", "confidence", "presentation", "retention", "inputs",
                      "status", "source", "uncertainty", "residuals", "validation", "scope", "failure_conditions", "fields"}
    page = render_diagnosis(synthetic_case())
    assert page.startswith("<!DOCTYPE html>") and page.count("<svg") == 3 and "이상 징후 2건" in page and "http" not in page
    out = tmp_path / "demo.html"
    demo_main(["--out", str(out)])
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


# ---- D2: 압력·유동계, 열관리계, 공정 동작·사이클, 설비 단위 진단 ----
from cont.packs.diagnosis import diagnose_equipment, load_site  # noqa: E402
from cont.packs.diagnosis.demo import synthetic_equipment  # noqa: E402
from cont.packs.diagnosis.profile import modules  # noqa: E402
from cont.view import render_equipment  # noqa: E402

PF = ({"pressure": "pressure", "flow": "flow", "dp": "pressure_drop"}, {"setpoint": "setpoint", "pump": "speed"})
TH = ({"error": "tracking_error", "heater": "heater_output", "coolant": "coolant_delta"}, {"setpoint": "setpoint", "ambient": "ambient"})
CY = ({"cycle_time": "cycle_time", "clamp_time": "step_time", "peak": "peak_load", "stop_error": "position_error"},
      {"setting": "speed_setting", "load": "load"})


def test_four_common_modules_exist_and_normal_operation_raises_no_alarm_in_any():
    assert modules() == ["cycle", "drive", "pressure_flow", "thermal"]
    cases = [("pressure_flow", syn.pressure_flow(3000, seed=11), syn.pressure_flow(2000, seed=13), PF, "t"),
             ("thermal", syn.thermal(3000, seed=21), syn.thermal(2000, seed=23), TH, "t"),
             ("cycle", syn.cycle(900, seed=31), syn.cycle(600, seed=33), CY, "cycle")]
    for mod, normal, cur, (sig, cond), t in cases:
        d = diagnose(mod, normal, cur, sig, cond, time=t)
        assert sum(len(r.intervals) for r in d.signals) == 0, mod


def test_pressure_flow_names_flow_decrease_and_restriction_increase():
    cur = syn.inject(syn.pressure_flow(2000, seed=12), "flow", 1500, 2000, -2.5)
    cur = syn.inject(cur, "dp", 1000, 1400, 0.4)
    d = diagnose("pressure_flow", syn.pressure_flow(3000, seed=11), cur, *PF, time="t")
    by = {r.role: r.intervals for r in d.signals}
    assert not by["pressure"]
    assert [(i.start, i.end, i.direction) for i in by["flow"]] == [(1500, 1999, "down")]
    assert [(i.start, i.end, i.direction) for i in by["pressure_drop"]] == [(1000, 1399, "up")]
    assert d.answer.value("change_flow_decrease") < 0 < d.answer.value("change_restriction_increase")


def test_thermal_names_extra_heating_effort_and_tracking_error_in_each_direction():
    cur = syn.inject(syn.thermal(2000, seed=22), "heater", 700, 1100, 6.0)
    cur = syn.inject(cur, "error", 1500, 1700, -4.0)
    d = diagnose("thermal", syn.thermal(3000, seed=21), cur, *TH, time="t")
    keys = {q.key for q in d.answer.quantities if q.key.startswith("change_")}
    assert keys == {"change_heating_effort_increase", "change_tracking_under"}
    assert d.answer.value("first_anomaly_time") == 700.0


def test_cycle_module_works_on_one_row_per_cycle():
    cur = syn.inject(syn.cycle(600, seed=32), "cycle_time", 380, 600, 0.35)
    d = diagnose("cycle", syn.cycle(900, seed=31), cur, *CY, time="cycle")
    (iv,) = d.signals[0].intervals
    assert (iv.start, iv.end) == (380, 599) and d.answer.get("change_cycle_slowdown").label.startswith("사이클 지연")
    assert all(not r.intervals for r in d.signals[1:])


def test_equipment_diagnosis_says_which_system_changed_and_renders_one_screen():
    eq = synthetic_equipment()
    a = eq.answer
    assert (a.value("systems_checked"), a.value("systems_with_anomaly")) == (4, 3)
    assert a.value("system3_anomaly_intervals") == 0 and a.value("system1_change_load_increase") > 4
    assert any(b.startswith("[가열 구역] 모든 신호가") for b in a.basis) and any(b.startswith("[동작 사이클]") and "사이클 지연" in b for b in a.basis)
    assert [s["module"] for s in a.inputs["systems"]] == ["drive", "pressure_flow", "thermal", "cycle"]
    page = render_equipment(eq)
    assert page.startswith("<!DOCTYPE html>") and "계통 4개 가운데 3개에서 이상 징후" in page and "http" not in page
    assert page.count('class="syscard') == 4 and page.count("<svg") == 13 and 'href="#sys4"' in page and 'id="sys4"' in page
    ans = packs.get("diagnosis").solve({"equipment": "x", "systems": [
        {"name": "A", "module": "cycle", "normal": syn.cycle(900, seed=31), "current": syn.cycle(600, seed=33), "signals": CY[0], "conditions": CY[1]}]})
    assert ans.value("systems_with_anomaly") == 0
    with pytest.raises(ValueError):
        diagnose_equipment([])


def test_site_file_connects_csv_columns_to_roles_without_code_change(tmp_path):
    def write(name, data):
        keys = list(data)
        (tmp_path / name).write_text(",".join(keys) + "\n" + "\n".join(",".join(repr(float(data[k][i])) for k in keys)
                                     for i in range(len(data[keys[0]]))), encoding="utf-8")
    ren = {"current": "MTR01_A", "load": "LOAD_PCT", "speed": "RPM"}
    write("n.csv", {ren.get(k, k): v for k, v in syn.drive(1500, seed=1).items()})
    write("c.csv", {ren.get(k, k): v for k, v in syn.inject(syn.drive(800, seed=5), "current", 300, 500, 1.0).items()})
    (tmp_path / "site.yaml").write_text(
        "equipment: 3호기\nsystems:\n  - name: 주축 구동부\n    module: drive\n    normal: n.csv\n    current: c.csv\n    time: t\n"
        "    signals: {MTR01_A: current}\n    conditions: {LOAD_PCT: load, RPM: speed}\n", encoding="utf-8")
    name, systems = load_site(tmp_path / "site.yaml")
    eq = diagnose_equipment(systems, name)
    assert eq.equipment == "3호기" and eq.systems[0].name == "주축 구동부" and eq.systems[0].interval_count == 1
    out = tmp_path / "r.html"
    demo_main(["--site", str(tmp_path / "site.yaml"), "--out", str(out)])
    assert "주축 구동부" in out.read_text(encoding="utf-8")
    demo_main(["--only", "drive", "--out", str(out)])
    assert "이상 징후 2건" in out.read_text(encoding="utf-8")
