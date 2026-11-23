"""형상 명세 → CAD 솔리드와 STEP 파일. CAD 엔진(OpenCascade의 파이썬 묶음 OCP)이 있어야 한다.

설치:  pip install -e .[cad]     (cadquery-ocp. 저장소의 가상환경 안에만 설치한다)

화면용 메시와 같은 형상 명세에서 만든다. 원은 진짜 원통면, 육각은 평면 여섯 개인 솔리드라 CAD에서 치수를 재고 고칠 수 있다.
화면용으로 잘라 낸 각도(sweep)는 무시하고 온전한 부품을 낸다.
"""
from __future__ import annotations

import math
from pathlib import Path

from cont.shape.spec import Assembly, Part


def available() -> bool:
    try:
        import OCP  # noqa: F401
    except ImportError:
        return False
    return True


def _require() -> None:
    if not available():
        raise RuntimeError("CAD 엔진(OCP)이 설치되어 있지 않다. 저장소 가상환경에서 `pip install -e .[cad]`를 실행한다")


def _quiet() -> None:
    """CAD 엔진이 파일을 쓸 때 화면에 쏟는 진행 글을 끈다 (실패 알림은 남긴다)."""
    try:
        from OCP.Message import Message, Message_Gravity
        for printer in Message.DefaultMessenger_s().Printers():
            printer.SetTraceLevel(Message_Gravity.Message_Fail)
    except Exception:       # 버전에 따라 이 기능이 없어도 내보내기는 된다
        pass


def solid(part: Part):
    """부품 하나의 솔리드 (TopoDS_Shape)."""
    _require()
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec

    axis = gp_Ax2(gp_Pnt(0, 0, part.z0), gp_Dir(0, 0, 1))
    if part.profile == "circle":
        body = BRepPrimAPI_MakeCylinder(axis, part.outer / 2, part.height).Shape()
    else:
        r = part.outer / math.sqrt(3)                           # 꼭짓점까지의 거리
        poly = BRepBuilderAPI_MakePolygon()
        for k in range(6):                                      # 평면 하나가 +x를 향하도록 꼭짓점은 30도에서 시작 (메시와 같은 방향)
            a = math.radians(30 + 60 * k)
            poly.Add(gp_Pnt(r * math.cos(a), r * math.sin(a), part.z0))
        poly.Close()
        body = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire()).Face(), gp_Vec(0, 0, part.height)).Shape()
    if part.inner > 0:
        hole = BRepPrimAPI_MakeCylinder(axis, part.inner / 2, part.height).Shape()
        body = BRepAlgoAPI_Cut(body, hole).Shape()
    return body


def solid_volume(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def write_step(assembly: Assembly, path: str | Path) -> list[tuple[str, float]]:
    """조립체를 STEP 파일로 쓴다 (부품마다 이름이 붙은 솔리드, 단위 mm). (부품 역할, 솔리드 부피) 목록을 돌려준다."""
    _require()
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    _quiet()
    doc = TDocStd_Document(TCollection_ExtendedString("cont"))
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    out = []
    for part in assembly.parts:
        s = solid(part)
        label = shapes.AddShape(s, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(part.role))    # 파일 안의 이름은 영어 식별자로 둔다 (CAD 프로그램 사이의 글자 깨짐을 피한다)
        out.append((part.role, solid_volume(s)))
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(doc) or writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP 파일을 쓰지 못했다: {path}")
    return out


def read_step_volumes(path: str | Path) -> list[float]:
    """STEP 파일을 다시 읽어 솔리드별 부피를 낸다. 내보낸 파일을 확인하는 데 쓴다."""
    _require()
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    _quiet()
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP 파일을 읽지 못했다: {path}")
    reader.TransferRoots()
    vols = []
    exp = TopExp_Explorer(reader.OneShape(), TopAbs_SOLID)
    while exp.More():
        vols.append(solid_volume(exp.Current())); exp.Next()
    return vols
