import pytest

from cont.generation import GenerationError, get_generator
from cont.objspec import ObjectSpecError, ViewState, affected, check, generate_image, hybrid_bonding_stack, image_prompt, image_request

S = hybrid_bonding_stack()


def test_prompt_lists_every_part_bottom_to_top():
    text, neg = image_prompt(S)
    order = [text.index("silicon layer (wafer side)"), text.index("thin dielectric oxide layer (wafer side)"),
             text.index("thin dielectric oxide layer (die side)"), text.index("silicon layer (die side)")]
    assert order == sorted(order)
    assert "not to scale" in text and "text" in neg


def test_prompt_follows_z_order_not_list_order():
    moved = S.edit_part("die.si", z0=-1.0, z1=-0.5)          # 맨 아래로 내림
    text, _ = image_prompt(moved)
    assert text.index("silicon layer (die side)") < text.index("silicon layer (wafer side)")


def test_stage_changes_only_the_scene_sentence():
    a, b = image_prompt(S, "approach")[0], image_prompt(S, "contact")[0]
    assert a != b and a.split("upper die")[0] == b.split("upper die")[0]
    assert image_prompt(S, 3)[0] == b and image_prompt(S, "접촉")[0] == b
    with pytest.raises(ObjectSpecError):
        image_prompt(S, "없는단계")


def test_request_is_validated_and_deterministic():
    r1, r2 = image_request(S, "align", seed=3), image_request(S, "align", seed=3)
    assert r1 == r2 and r1.seed == 3 and r1.negative_prompt
    with pytest.raises(GenerationError):
        image_request(S, width=100)


def test_generate_links_image_to_spec_and_marks_fake_as_not_real():
    out = generate_image(S, get_generator("fake"), "contact", rep_id="img1")
    assert out.record["real"] is False
    link = out.record["object_spec"]
    assert link["spec_version"] == S.version and link["stage"] == "contact" and link["parts_declared_by"] == "prompt"
    assert link["parts"] == ["wafer.si", "wafer.dielectric", "die.dielectric", "die.si"]
    assert out.representation.kind == "image" and check(S, out.representation).ok
    assert out.record["sha256"] == out.result.sha256


def test_editing_a_part_makes_the_image_stale_and_selects_it_for_rebuild():
    out = generate_image(S, get_generator("fake"))
    new = S.edit_part("die.si", z1=2.4)
    assert check(new, out.representation).stale
    assert affected(S, new, [out.representation]) == {"image": ["die.si"]}


def test_camera_and_speed_changes_do_not_touch_the_image():
    out = generate_image(S, get_generator("fake"))
    v = ViewState().with_camera(azimuth=90.0).with_speed(S, 2, 0.5)
    assert v is not None and check(S, out.representation).ok and affected(S, S, [out.representation]) == {}
