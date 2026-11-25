import dataclasses

import pytest

from cont.generation import get_generator
from cont.objspec import (ObjectSpecError, Representation, SelectionError, ViewState, check, edit_selection, generate_image,
                          hybrid_bonding_stack, overlaps, select, select_region)
from cont.view.scene4d import scene_data

S = hybrid_bonding_stack()


def test_select_by_id_name_layer_and_partial_name():
    assert select(S, "die.si").parts == ("die.si",) and select(S, "die.si").how == "id"
    assert select(S, "위 다이(실리콘)").parts == ("die.si",) and select(S, "위 다이").parts == ("die.si",)
    lay = select(S, "die")
    assert lay.how == "layer" and lay.parts == ("die.dielectric", "die.si")


def test_ambiguous_or_missing_reference_is_refused_with_candidates():
    with pytest.raises(SelectionError) as e:
        select(S, "유전층")                     # 아래·위 유전층 둘 다 해당
    assert set(e.value.candidates) == {"wafer.dielectric", "die.dielectric"}
    with pytest.raises(SelectionError) as e2:
        select(S, "없는부품")
    assert set(e2.value.candidates) == set(S.part_ids)
    for bad in ("", "  ", None):
        with pytest.raises(SelectionError):
            select(S, bad)


def test_region_picks_parts_by_cover_or_center():
    assert select_region(S, (0.3, 0.0, 0.7, 0.1)).parts == ("die.si",)               # 맨 위 띠
    assert select_region(S, (0.0, 0.8, 1.0, 1.0)).parts == ("wafer.si",)             # 맨 아래 넓은 띠
    two = select_region(S, (0.0, 0.0, 1.0, 0.4))                                      # 위쪽 40%: 다이 두 층
    assert set(two.parts) == {"die.si", "die.dielectric"}
    with pytest.raises(SelectionError):
        select_region(S, (0.5, 0.5, 0.4, 0.6))                                       # 뒤집힌 사각형
    with pytest.raises(SelectionError):
        select_region(S, (0.0, 0.0, 0.05, 0.05))                                     # 부품 밖 모서리


def test_edit_changes_only_selected_part_and_reports_before_after():
    r = edit_selection(S, select(S, "위 다이"), z1=2.4)
    assert r.changed == ("die.si",) and r.diff == {"die.si": {"z1": (2.0, 2.4)}}
    assert set(r.unchanged) == {"wafer.si", "wafer.dielectric", "die.dielectric"}
    for pid in r.unchanged:                                                          # 선택 밖은 값이 같다
        assert dataclasses.asdict(r.old.part(pid)) == dataclasses.asdict(r.new.part(pid))
    assert r.version_changed and r.new.parent_version == S.version and r.new.dimension_status == "user_input"
    assert S.part("die.si").part.z1 == 2.0                                           # 원본은 그대로


def test_layer_edit_applies_to_each_part_and_keeps_parent_version():
    r = edit_selection(S, select(S, "die"), outer=16.0)
    assert set(r.changed) == {"die.dielectric", "die.si"} and r.new.parent_version == S.version


def test_one_name_for_many_parts_is_refused_and_unknown_field_too():
    with pytest.raises(SelectionError):
        edit_selection(S, select(S, "die"), name="같은 이름")
    with pytest.raises(ObjectSpecError):
        edit_selection(S, select(S, "die.si"), color="red")


def test_same_value_edit_changes_nothing():
    r = edit_selection(S, select(S, "die.si"), z1=2.0)
    assert r.changed == () and not r.version_changed


def test_rebuild_selects_only_representations_that_point_at_the_edited_part():
    img = generate_image(S, get_generator("fake"), rep_id="image").representation
    graph = Representation("die_graph", "graph", S.version, ("die.dielectric",))
    r = edit_selection(S, select(S, "die.si"), z1=2.4)
    assert r.rebuild([img, graph]) == {"image": ["die.si"]}                          # 그래프는 건드리지 않는다
    assert check(r.new, img).stale


def test_3d_scene_changes_only_the_edited_part_after_selection_edit():
    r = edit_selection(S, select(S, "die.si"), z1=2.4)
    a, b = scene_data(S), scene_data(r.new)
    assert [x["id"] for x, y in zip(a["parts"], b["parts"]) if x["tri"] != y["tri"]] == ["die.si"]
    assert scene_data(r.new, ViewState().with_speed(r.new, 2, 0.5))["spec_version"] == r.new.version


def test_stage_pose_edit_changes_one_stage_of_one_part():
    n = S.edit_stage_pose("정렬", "die.si", dx=0.3)
    assert n.stage("align").pose_of("die.si").dx == 0.3 and n.stage("align").pose_of("die.si").dz == 2.0
    assert n.stage("approach") == S.stage("approach") and n.stage("contact") == S.stage("contact")
    assert n.stage("align").pose_of("die.dielectric") == S.stage("align").pose_of("die.dielectric")
    assert n.changed_parts(S) == () and n.version != S.version                      # 부품 모양은 같고 구조(단계)만 다르다
    for bad in (dict(dz=1, color=2), {}):
        with pytest.raises(ObjectSpecError):
            S.edit_stage_pose(1, "die.si", **bad)
    with pytest.raises(ObjectSpecError):
        S.edit_stage_pose(1, "nope", dz=1)


def test_overlap_after_edit_is_reported_not_blocked():
    r = edit_selection(S, select(S, "die.si"), z0=1.0)
    assert ("wafer.dielectric", "die.si") in overlaps(r.new) and overlaps(S) == []
