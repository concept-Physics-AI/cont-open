import dataclasses

import pytest

from cont.objspec import (ObjectSpec, ObjectSpecError, ObjPart, Pose, Representation, Stage, ViewState, affected, check,
                          hybrid_bonding_stack)
from cont.shape import Part, assembly_mesh


def _rep(spec, rid, kind, refs=None, names=False, version=None):
    refs = tuple(spec.part_ids if refs is None else refs)
    nm = tuple((i, spec.part(i).part.name) for i in refs) if names else ()
    return Representation(rid, kind, version or spec.version, refs, nm)


def test_template_has_unique_ids_stages_and_illustrative_status():
    s = hybrid_bonding_stack()
    assert len(set(s.part_ids)) == 4 and [x.id for x in s.stages] == ["approach", "align", "contact"]
    assert s.dimension_status == "illustrative" and s.time_axis == "process_stage"


@pytest.mark.parametrize("bad", ["", "Wafer", "1abc", "a b", "a..b", "a-b", "a."])
def test_bad_ids_refused(bad):
    with pytest.raises(ObjectSpecError):
        ObjPart(bad, Part("x", "r", 0, 1, 5))


def test_duplicate_ids_and_unknown_stage_part_refused():
    p = ObjPart("a", Part("x", "r", 0, 1, 5))
    with pytest.raises(ObjectSpecError, match="겹칩니다"):
        ObjectSpec("n", (p, p))
    with pytest.raises(ObjectSpecError, match="없는 부품"):
        ObjectSpec("n", (p,), (Stage("s", "단계", (("zzz", Pose()),)),))
    with pytest.raises(ObjectSpecError, match="단계 ID"):
        ObjectSpec("n", (p,), (Stage("s", "a"), Stage("s", "b")))
    with pytest.raises(ObjectSpecError, match="부품이 하나도"):
        ObjectSpec("n", ())


def test_version_is_content_hash_and_ignores_parent():
    a, b = hybrid_bonding_stack(), hybrid_bonding_stack()
    assert a.version == b.version
    assert dataclasses.replace(a, parent_version="x" * 64).version == a.version
    assert hybrid_bonding_stack(gap=3.0).version != a.version      # 단계 자세가 달라지면 구조가 다르다


def test_edit_makes_new_spec_keeps_original_and_links_parent():
    s = hybrid_bonding_stack()
    n = s.edit_part("die.si", z1=2.4)
    assert s.part("die.si").part.z1 == 2.0 and n.part("die.si").part.z1 == 2.4
    assert n.version != s.version and n.parent_version == s.version
    assert s.changed_parts(n) == ("die.si",) and s.changed_parts(s) == ()
    assert n.dimension_status == "user_input"       # 설명용 치수를 사용자가 고쳤다


def test_edit_refuses_unknown_part_field_or_invalid_geometry():
    s = hybrid_bonding_stack()
    with pytest.raises(ObjectSpecError, match="없는 부품"):
        s.edit_part("nope", z1=3)
    with pytest.raises(ObjectSpecError, match="고칠 수 없는"):
        s.edit_part("die.si", role="bolt")
    with pytest.raises(ValueError):
        s.edit_part("die.si", z1=1.0)                     # 아래 면보다 낮다


def test_spec_feeds_existing_3d_mesh():
    ms = assembly_mesh(hybrid_bonding_stack().to_assembly())
    assert len(ms) == 4 and all(len(m.faces) > 0 for _, m in ms)


def test_view_state_changes_do_not_touch_structure_version():
    s = hybrid_bonding_stack()
    v = ViewState().with_camera(azimuth=120.0).with_speed(s, "align", 0.5)
    assert v.speed_of("align") == 0.5 and v.speed_of("approach") == 1.0 and v.azimuth == 120.0
    assert s.version == hybrid_bonding_stack().version


@pytest.mark.parametrize("kw", [{"azimuth": 400}, {"elevation": 95}, {"distance": 0}])
def test_view_state_ranges(kw):
    with pytest.raises(ObjectSpecError):
        ViewState(**kw)


def test_speed_needs_known_stage_and_sane_factor():
    s = hybrid_bonding_stack()
    with pytest.raises(ObjectSpecError, match="찾지 못했"):
        ViewState().with_speed(s, "zzz", 0.5)
    for f in (0, 0.01, 50, -1):
        with pytest.raises(ObjectSpecError):
            ViewState().with_speed(s, "align", f)


def test_check_clean_representation_is_ok():
    s = hybrid_bonding_stack()
    r = check(s, _rep(s, "scene3d", "scene3d", names=True))
    assert r.ok and not r.needs_review


def test_check_finds_missing_unknown_renamed_and_stale():
    s = hybrid_bonding_stack()
    rep = Representation("img", "image", "oldversion", ("wafer.si", "wafer.dielectric", "die.si", "ghost"),
                         (("die.si", "윗 다이"),))
    r = check(s, rep)
    assert r.missing == ["die.dielectric"] and r.unknown == ["ghost"] and r.stale
    assert r.renamed == [("die.si", "위 다이(실리콘)", "윗 다이")] and r.needs_review


def test_partial_representation_allowed_when_not_expecting_all():
    s = hybrid_bonding_stack()
    rep = _rep(s, "graph", "graph", refs=["wafer.si"])
    assert not check(s, rep).ok and check(s, rep, expect_all=False).ok


def test_affected_only_representations_that_reference_changed_parts():
    s = hybrid_bonding_stack()
    n = s.edit_part("die.si", z1=2.4)
    reps = [_rep(s, "scene3d", "scene3d"), _rep(s, "wafer_graph", "graph", refs=["wafer.si"]),
            _rep(s, "explain", "text", refs=[])]
    assert affected(s, n, reps) == {"scene3d": ["die.si"]}
    assert affected(s, s, reps) == {}                       # 구조가 같으면 아무것도 다시 만들지 않는다


def test_affected_includes_removed_and_added_parts():
    s = hybrid_bonding_stack()
    fewer = dataclasses.replace(s, parts=s.parts[:3], stages=(), start=())
    reps = [_rep(s, "r1", "scene3d", refs=["die.si"]), _rep(s, "r2", "graph", refs=["wafer.si"])]
    assert affected(s, fewer, reps) == {"r1": ["die.si"]}


def test_stage_poses_default_to_original_place():
    s = hybrid_bonding_stack()
    approach = s.stages[0]
    assert approach.pose_of("wafer.si") == Pose() and approach.pose_of("die.si").dz == 2.0
    assert s.stages[2].pose_of("die.si") == Pose()


def test_spec_and_view_round_trip_through_dict():
    from cont.objspec import ObjectSpec, ViewState, hybrid_bonding_stack
    s = hybrid_bonding_stack().edit_part("die.si", z1=2.4)
    t = ObjectSpec.from_dict(s.to_dict(), s.parent_version)
    assert t == s and t.version == s.version
    v = ViewState().with_camera(azimuth=-40.0).with_speed(s, 2, 0.5)
    assert ViewState.from_dict(v.to_dict()) == v
    for bad in ({}, {"name": "x"}, {"name": "x", "parts": [{"id": "BAD", "layer": "", "name": "a", "role": "r", "z0": 0, "z1": 1, "outer": 1}]}):
        with pytest.raises(ObjectSpecError):
            ObjectSpec.from_dict(bad)
    with pytest.raises(ObjectSpecError):
        ViewState.from_dict({"azimuth": 1})
