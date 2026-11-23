import json
import math
import re

import numpy as np
import pytest

from cont.dialogue.fastening_chat import Session
from cont.dialogue.serve_fastening import example, page
from cont.packs.fastening.shape import bolt_length, joint_shape
from cont.shape import Assembly, Part, assembly_mesh, part_mesh, volume
from cont.view import render_fastening
from cont.view.viewer3d import viewer, viewer_data


def closed_and_outward(mesh) -> bool:
    """모든 모서리를 두 면이 서로 반대 방향으로 한 번씩 지나면 닫힌 메시이고 면의 방향이 한결같다."""
    count = {}
    for tri in mesh.faces.tolist():
        for k in range(3):
            e = (tri[k], tri[(k + 1) % 3])
            count[e] = count.get(e, 0) + 1
    return all(c == 1 and count.get((b, a)) == 1 for (a, b), c in count.items())


@pytest.mark.parametrize("part", [
    Part("원기둥", "x", 0, 10, 12),
    Part("관", "x", -5, 5, 40, 13.5),
    Part("잘라 낸 관", "x", 0, 20, 40, 13.5, sweep=270),
    Part("잘라 낸 원기둥", "x", 0, 20, 40, sweep=90),
    Part("육각기둥", "x", 0, 7.5, 18, profile="hexagon"),
    Part("너트", "x", 0, 10.8, 18, 12, profile="hexagon"),
])
def test_part_mesh_is_closed_faces_outward_and_has_the_right_volume(part):
    m = part_mesh(part)
    assert closed_and_outward(m)
    assert volume(m) == pytest.approx(part.exact_volume, rel=0.006)        # 원을 36각형으로 나눈 만큼만 다르다
    assert m.vertices[:, 2].min() == part.z0 and m.vertices[:, 2].max() == part.z1


def test_hexagon_has_its_true_corners_and_flats():
    m = part_mesh(Part("머리", "x", 0, 5, 16, profile="hexagon"))
    r = np.hypot(m.vertices[:, 0], m.vertices[:, 1])
    assert r.max() == pytest.approx(16 / math.sqrt(3)) and r[r > 0].min() == pytest.approx(8.0)   # 꼭짓점까지, 평면까지
    assert volume(m) == pytest.approx(math.sqrt(3) / 2 * 16 ** 2 * 5, rel=1e-9)                # 속이 찬 육각기둥은 정확하다


def test_spec_rejects_shapes_that_cannot_exist():
    for kw in (dict(z0=5, z1=5, outer=10), dict(z0=0, z1=5, outer=10, inner=10), dict(z0=0, z1=5, outer=10, sweep=0),
               dict(z0=0, z1=5, outer=10, profile="square"), dict(z0=0, z1=5, outer=10, profile="hexagon", sweep=270)):
        with pytest.raises(ValueError):
            Part("x", "x", **kw)
    with pytest.raises(ValueError):
        part_mesh(Part("x", "x", 0, 1, 10), segments=10)


def test_joint_shape_follows_the_joint_dimensions_and_the_standard_table():
    j, _ = example()                                     # M10, 판 15 + 15
    a = joint_shape(j)
    assert [p.role for p in a.parts] == ["bolt_head", "bolt_shank", "plate_head", "plate_nut", "nut"]
    head, shank, p1, p2, nut = a.parts
    assert (head.outer, head.profile, nut.inner) == (16.0, "hexagon", 10.0)
    assert head.height == pytest.approx(6.4) and nut.height == pytest.approx(8.4)
    assert (p1.z0, p1.z1, p2.z0, p2.z1) == (0.0, 15.0, -15.0, 0.0) and p1.outer == 40.0 and p1.inner == 11.0
    assert head.z0 == p1.z1 and nut.z1 == p2.z0                               # 머리와 너트가 판에 닿는다
    assert bolt_length(j) == pytest.approx(30 + 8.4 + 2 * 1.5) and shank.height == pytest.approx(bolt_length(j))
    assert shank.z0 < nut.z0                                                  # 나사 끝이 너트 밖으로 나온다
    assert all(closed_and_outward(m) for _, m in assembly_mesh(a))
    opened = a.opened(("plate_head", "plate_nut"))
    assert [p.sweep for p in opened.parts] == [360.0, 360.0, 270.0, 270.0, 360.0] and a.part("plate_head").sweep == 360.0
    assert opened.part("plate_head").exact_volume == pytest.approx(0.75 * p1.exact_volume)


def test_changing_the_joint_by_conversation_changes_the_shape():
    s = Session(*example())
    before = joint_shape(s.joint)
    s.say("M16으로 바꾸고 머리 쪽 판 두께 25, 바깥지름 60")
    after = joint_shape(s.joint)
    assert (before.part("bolt_shank").outer, after.part("bolt_shank").outer) == (10.0, 16.0)
    assert after.part("plate_head").height == 25.0 and after.part("plate_head").outer == 60.0 and after.part("plate_head").inner == 17.5
    assert after.part("bolt_head").outer == 24.0 and after.name == "M16 볼트 조인트"
    html_text = page(s, None)
    assert "M16 볼트 조인트" in html_text and "<canvas" in html_text


def test_viewer_carries_every_part_and_needs_no_outside_resource():
    j, l = example()
    a = joint_shape(j)
    d = viewer_data(a)
    assert [p["role"] for p in d["parts"]] == [p.role for p in a.parts] and d["center"] == [0.0, 0.0, pytest.approx((21.4 - 26.4) / 2)]
    for p, (_, m) in zip(d["parts"], assembly_mesh(a)):
        assert len(p["tri"]) == len(m.faces) * 9 and p["color"].startswith("--")
    z = np.array(d["parts"][0]["tri"]).reshape(-1, 3)[:, 2]
    assert np.abs(z - d["center"][2]).max() < d["radius"]                       # 화면에 다 들어온다
    frag = viewer(a, legend=(("볼트·너트", "--sig"),))
    assert frag.count("<canvas") == 1 and 'tabindex="0"' in frag and "화살표 키" in frag and "볼트·너트" in frag
    assert json.loads(re.search(r'<script type="application/json">(.*?)</script>', frag, re.S).group(1))["radius"] == d["radius"]
    from cont.packs.fastening import answer
    page_html = render_fastening(j, l, answer(j, l))
    assert "3D 형상" in page_html and page_html.count("<canvas") == 1 and "getContext('webgl'" in page_html and "http" not in page_html
    assert "3D 보기를 쓸 수 없습니다" in page_html                             # WebGL이 없을 때의 안내가 들어 있다
