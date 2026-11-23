import re
import threading
import urllib.request

import numpy as np
import pytest

from cont.dialogue.fastening_chat import Session
from cont.dialogue.serve_fastening import example, make_server, page
from cont.packs.fastening.export import export_step, export_stl, main
from cont.packs.fastening.shape import joint_shape
from cont.shape import Part, Assembly, cad_ocp, step
from cont.shape.stl import read_stl, write_stl

needs_cad = pytest.mark.skipif(not cad_ocp.available(), reason="CAD 엔진(OCP)이 없다: pip install -e .[cad]")


def entities(text: str) -> dict[str, str]:
    return dict(re.findall(r"^(#\d+)=(.*);$", text, re.M))


def test_stl_export_needs_no_extra_install_and_keeps_the_shape(tmp_path):
    a = joint_shape(example()[0])
    out = tmp_path / "j.stl"
    n = write_stl(a, out)
    tris = read_stl(out)
    assert n == len(tris) == 1152 and out.stat().st_size == 84 + 50 * n
    vol = float(np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum() / 6)
    assert vol == pytest.approx(sum(p.exact_volume for p in a.parts), rel=0.006)
    assert tris[:, :, 2].min() == pytest.approx(a.z_range[0], abs=1e-3) and tris[:, :, 2].max() == pytest.approx(a.z_range[1], abs=1e-3)
    assert export_stl(example()[0].modified(size="M16"), tmp_path / "k.stl") == n


def test_native_step_has_one_named_solid_per_part_and_every_shell_is_closed():
    """CAD 엔진 없이 확인할 수 있는 것: 파일의 뼈대, 부품 이름, 면의 수, 그리고 모든 모서리를 두 면이 서로 반대 방향으로 한 번씩 쓰는지."""
    a = joint_shape(example()[0])
    text = step.step_text(a, timestamp="2026-11-23T00:00:00")
    assert text.startswith("ISO-10303-21;\nHEADER;") and text.endswith("ENDSEC;\nEND-ISO-10303-21;\n") and text.isascii()
    assert "AUTOMOTIVE_DESIGN" in text and "SI_UNIT(.MILLI.,.METRE.)" in text
    assert step.step_text(a, timestamp="2026-11-23T00:00:00") == text                          # 같은 형상이면 같은 파일
    ent = entities(text)
    assert all(ref in ent for body in ent.values() for ref in re.findall(r"#\d+", body))        # 가리키는 번호가 모두 있다
    products = re.findall(r"PRODUCT\('([a-z_]+)'", text)
    assert products == [p.role for p in a.parts]
    faces_per_solid = []
    for body in ent.values():
        if body.startswith("CLOSED_SHELL"):
            faces = re.findall(r"#\d+", body)
            faces_per_solid.append(len(faces))
            use: dict[str, list[str]] = {}
            for f in faces:
                for bound in re.findall(r"#\d+", ent[f].split("),")[0]):
                    loop = re.findall(r"#\d+", ent[bound])[0]
                    for oe in re.findall(r"#\d+", ent[loop]):
                        edge, sense = re.search(r"ORIENTED_EDGE\('',\*,\*,(#\d+),(\.[TF]\.)\)", ent[oe]).groups()
                        use.setdefault(edge, []).append(sense)
            assert all(sorted(s) == [".F.", ".T."] for s in use.values())
    assert faces_per_solid == [8, 4, 6, 6, 10]            # 머리 6+2, 축 2+2, 판 (바깥 2 + 구멍 2 + 2) 둘, 너트 6+2+2


def test_step_numbers_are_valid_step_reals():
    assert [step._num(v) for v in (5, 0.5, -15.0, 1e-7, 1234567.0, 1 / 3)] == ["5.", "0.5", "-15.", "1.E-07", "1234567.", "0.333333333333"]
    text = step.step_text(Assembly("이름 'x'", (Part("p", "p", 0, 1, 10),)))
    assert "FILE_NAME('__ _x_'" in text                    # 파일 안에는 ASCII만 쓴다


def test_export_and_server_give_step_without_any_cad_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(cad_ocp, "available", lambda: False)
    out = tmp_path / "j.step"
    main(["--step", str(out), "--size", "M16"])
    assert out.read_text(encoding="ascii").count("MANIFOLD_SOLID_BREP") == 5
    with pytest.raises(SystemExit, match="--engine 을 빼면"):
        main(["--step", str(out), "--engine", "ocp"])
    with pytest.raises(ValueError):
        export_step(example()[0], str(out), engine="freecad")
    with pytest.raises(RuntimeError, match="pip install -e .\\[cad\\]"):
        cad_ocp.write_step(joint_shape(example()[0]), out)
    s = Session(*example()); s.say("M12로 바꿔")
    assert 'href="/joint.step"' in page(s, "/say") and "joint.step" not in page(s, None)       # 파일로 낸 화면에는 받기 링크가 없다
    srv = make_server(s, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        r = urllib.request.urlopen(base + "/joint.step", timeout=10)
        assert r.headers["Content-Disposition"] == 'attachment; filename="M12_joint.step"'
        assert r.read().startswith(b"ISO-10303-21;")
        assert urllib.request.urlopen(base + "/joint.stl", timeout=10).read()[:4] == b"ConT"
    finally:
        srv.shutdown(); srv.server_close()


@needs_cad
@pytest.mark.parametrize("size", ["M6", "M10", "M24"])
def test_cad_engine_reads_the_native_step_as_valid_solids_with_exact_volumes(tmp_path, size):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    a = joint_shape(example()[0].modified(size=size, outer_diameter=80.0))
    out = tmp_path / "n.step"
    assert step.write_step(a, out) == 5
    reader = STEPControl_Reader(); reader.ReadFile(str(out)); reader.TransferRoots()
    exp = TopExp_Explorer(reader.OneShape(), TopAbs_SOLID); vols = []
    while exp.More():
        assert BRepCheck_Analyzer(exp.Current()).IsValid()
        vols.append(cad_ocp.solid_volume(exp.Current())); exp.Next()
    assert vols == pytest.approx([p.exact_volume for p in a.parts], rel=1e-9)       # 부피가 양수이니 면이 바깥을 향한다


@needs_cad
def test_cad_engine_writer_and_native_writer_agree(tmp_path):
    a = joint_shape(example()[0])
    written = cad_ocp.write_step(a, tmp_path / "o.step")
    assert [r for r, _ in written] == [p.role for p in a.parts]
    step.write_step(a, tmp_path / "n.step")
    assert sorted(cad_ocp.read_step_volumes(tmp_path / "n.step")) == pytest.approx(sorted(cad_ocp.read_step_volumes(tmp_path / "o.step")), rel=1e-9)
    assert export_step(example()[0], str(tmp_path / "e.step"), engine="ocp") == 5
