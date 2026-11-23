"""공통 결과 형식: 값의 지위와 믿을 근거 (docs/hidden_physics.md)."""
from cont.answer import (IDENT_NONE, IDENT_OK, IDENT_WEAK, STATUS_ESTIMATED, STATUS_OBSERVED as OBSERVED, NOT_REPORTED, STATUS_GENERATED, STATUS_INPUT, STATUS_LABELS, STATUS_OBSERVED, STATUS_PREDICTED,
                         STATUS_SIMULATED, STATUS_UNSPECIFIED, Confidence, Field, PhysicsAnswer, Quantity, Residual)
from cont.packs.fastening import answer as fastening_answer
from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate

ROWS = ["값의 지위", "근거 데이터", "사용 모델", "가정", "증거와 식별가능성", "불확실성", "물리잔차", "검증 상태", "적용 범위", "실패 조건"]


def joint_and_load():
    steel = 205000.0
    return (BoltedJoint("M10", "10.9", Plate(15.0, steel, 700.0), Plate(15.0, steel, 700.0), outer_diameter=40.0),
            LoadCase(50.0, 0.12, 0.12, (0.10, 0.14), axial_load_max=6000.0, transverse_load=1500.0, friction_interface=0.15, embedding=0.008))


def test_an_answer_that_reports_nothing_says_so_instead_of_staying_silent():
    a = PhysicsAnswer("q", (Quantity("x", "값", 1.0, "-"),), "지식표", ("출처",), Confidence("low", "이유"))
    assert a.status == STATUS_UNSPECIFIED and a.status_of("x") == STATUS_UNSPECIFIED
    t = dict(a.trust())
    assert list(t) == ROWS and t["값의 지위"].startswith("지위 미정")
    assert all(t[k] == NOT_REPORTED for k in ("근거 데이터", "불확실성", "물리잔차", "적용 범위", "실패 조건"))
    assert t["검증 상태"] == "검증 전. 이유" and t["가정"] == "적어 둔 가정 없음"


def test_a_quantity_can_carry_its_own_status_and_the_bundle_lists_what_it_holds():
    a = PhysicsAnswer("q", (Quantity("d", "지름", 10.0, "mm", status=STATUS_INPUT), Quantity("s", "응력", 1.0, "MPa")), "해석식", (),
                      Confidence("medium", "r"), status=STATUS_SIMULATED,
                      residuals=(Residual("b", "평형", 0.0, "N", "닫힌 식"), Residual("m", "질량 보존", None, "kg")))
    assert a.status_of("d") == STATUS_INPUT and a.status_of("s") == STATUS_SIMULATED and a.statuses() == (STATUS_INPUT, STATUS_SIMULATED)
    t = dict(a.trust())
    assert t["값의 지위"] == "입력, 해석. 관측·추정한 값은 없음"
    assert t["물리잔차"] == f"평형 = 0 N. 닫힌 식; 질량 보존: {NOT_REPORTED}"
    assert a.to_dict()["residuals"][0]["key"] == "b" and a.to_dict()["quantities"][0]["status"] == STATUS_INPUT


def test_fastening_answer_is_simulated_from_inputs_with_force_balance_as_its_residual():
    j, l = joint_and_load()
    a = fastening_answer(j, l)
    assert a.status == STATUS_SIMULATED and a.statuses() == (STATUS_INPUT, STATUS_SIMULATED)
    assert a.status_of("clamp_length") == STATUS_INPUT and a.status_of("preload") == STATUS_SIMULATED
    (r,) = a.residuals
    assert r.key == "force_balance" and r.unit == "N" and abs(r.value) < 1e-6
    assert "마찰계수 0.1 ~ 0.14" in a.uncertainty and "편심 하중" in a.failure_conditions and a.scope.startswith("동심 체결")
    alone = fastening_answer(j, LoadCase(50.0, 0.12, 0.12))
    assert alone.uncertainty.startswith("마찰 범위를 주지 않아 반영하지 않음")


def test_every_pack_states_the_status_of_its_values():
    """팩이 낸 답은 지위를 비워 두지 않는다. 진단은 관측, 예측은 예측, 추천은 생성 후보."""
    from cont.packs.fastening.recommend import recommend
    j, l = joint_and_load()
    rec = recommend(j, l, {"safety_yield": 1.5})
    assert rec.answer.status == STATUS_GENERATED and STATUS_LABELS[rec.answer.status] == "생성 후보"
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "cont" / "packs"
    calls = [(p.name, m.group(0)) for p in root.rglob("*.py") for m in re.finditer(r"PhysicsAnswer\(\s*(status=STATUS_\w+)?", p.read_text(encoding="utf-8"))
             if "class PhysicsAnswer" not in m.group(0)]
    assert len(calls) >= 8 and all("status=STATUS_" in c for _, c in calls), calls
    assert {STATUS_OBSERVED, STATUS_PREDICTED} <= set(STATUS_LABELS)


def test_a_field_is_a_grid_of_values_with_its_own_status_and_holes_where_there_is_no_material():
    import pytest
    f = Field("p", "압력", "MPa", ("r", "z"), "mm", (1.0, 2.0, 3.0), (0.0, 5.0), ((1.0, None, 3.0), (-2.0, 0.5, None)), status=STATUS_SIMULATED)
    assert f.range() == (-2.0, 3.0)
    assert Field("e", "빈 장", "-", ("x", "y"), "mm", (0.0,), (0.0,), ((None,),)).range() is None
    with pytest.raises(ValueError):
        Field("bad", "틀린 격자", "-", ("x", "y"), "mm", (0.0, 1.0), (0.0,), ((1.0,),))
    a = PhysicsAnswer("q", (), "수치해석", (), Confidence("low", "r"), status=STATUS_INPUT, fields=(f,))
    assert a.field("p") is f and a.field_status("p") == STATUS_SIMULATED and a.to_dict()["fields"][0]["values"][0][1] is None
    with pytest.raises(KeyError):
        a.field("none")
    assert PhysicsAnswer("q", (), "m", (), Confidence("low", "r")).fields == ()


def test_an_estimate_points_at_its_evidence_and_says_how_well_it_can_be_told_apart():
    import pytest
    obs = Quantity("x", "늘어남", 0.1, "mm", status=OBSERVED)
    est = Quantity("f", "체결력", 3.0, "N", evidence=("x",), identifiability=IDENT_OK, identifiability_basis="상대 표준 불확도 5.0%")
    bare = Quantity("g", "다른 추정값", 1.0, "-")
    a = PhysicsAnswer("q", (obs, est, bare), "역문제", (), Confidence("low", "r"), status=STATUS_ESTIMATED)
    assert a.evidence_of("f") == (obs,) and a.evidence_of("g") == ()
    assert a.evidence_lines() == ["체결력 ← 늘어남. 식별가능성: 가려낼 수 있음 (상대 표준 불확도 5.0%)",
                                  f"다른 추정값 ← {NOT_REPORTED}. 식별가능성: {NOT_REPORTED}"]       # 관측값은 줄에 나오지 않는다
    assert dict(a.trust())["증거와 식별가능성"].startswith("체결력 ← 늘어남")
    assert dict(PhysicsAnswer("q", (obs,), "m", (), Confidence("low", "r"), status=STATUS_SIMULATED).trust())["증거와 식별가능성"] == "추정한 값 없음"
    with pytest.raises(ValueError, match="is not in this answer"):
        PhysicsAnswer("q", (Quantity("f", "체결력", 1.0, "N", evidence=("nope",)),), "m", (), Confidence("low", "r"))
    with pytest.raises(ValueError, match="identifiability must be one of"):
        PhysicsAnswer("q", (Quantity("f", "체결력", 1.0, "N", identifiability="0.83"),), "m", (), Confidence("low", "r"))
    assert {IDENT_OK, IDENT_WEAK, IDENT_NONE} == {"identifiable", "weak", "not_identifiable"}
