from cont.tolerance import check, load_profile


def test_default_profile_reports_only(monkeypatch):
    monkeypatch.delenv("CONT_TOLERANCE_PROFILE", raising=False)
    prof = load_profile()
    assert prof["torque_to_preload"].limit is None
    c = check(prof["torque_to_preload"], 102.0, 100.0)
    assert abs(c.deviation - 0.02) < 1e-12
    assert c.passed is None  # no decided limit -> no pass/fail


def test_profile_and_env_override(monkeypatch):
    prof = load_profile("example_lab")
    assert prof["dimension"].limit == 0.01
    assert prof["fatigue"].limit is None  # not set in profile -> inherits default
    monkeypatch.setenv("CONT_TOL__DIMENSION__LIMIT", "0.05")
    prof2 = load_profile("example_lab")
    assert prof2["dimension"].limit == 0.05
    assert check(prof2["dimension"], 10.03, 10.0).passed is True
