"""볼트 조인트의 형상을 파일로 낸다.

예제 조인트로:  python -m cont.packs.fastening.export --step joint.step --stl joint.stl
둘 다 추가 설치 없이 된다. STEP은 저장소 안의 코드가 직접 쓴다 (cont.shape.step).
CAD 엔진으로 쓰려면 --engine ocp (pip install -e .[cad] 필요. Windows의 Smart App Control이 켜진 PC에서는 되지 않는다).
"""
from __future__ import annotations

import argparse

from cont.packs.fastening.joint import BoltedJoint
from cont.packs.fastening.shape import joint_shape
from cont.shape import cad_ocp, step
from cont.shape.stl import write_stl


def export_step(joint: BoltedJoint, path: str, engine: str = "native") -> int:
    """부품 수를 돌려준다. engine: native(직접 쓰기, 기본) | ocp(CAD 엔진)."""
    if engine == "ocp":
        return len(cad_ocp.write_step(joint_shape(joint), path))
    if engine != "native":
        raise ValueError(f"unknown engine '{engine}'")
    return step.write_step(joint_shape(joint), path)


def export_stl(joint: BoltedJoint, path: str) -> int:
    return write_stl(joint_shape(joint), path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step"); ap.add_argument("--stl")
    ap.add_argument("--size", help="규격을 바꿔서 내기 (예: M16)")
    ap.add_argument("--engine", choices=("native", "ocp"), default="native")
    a = ap.parse_args(argv)
    from cont.dialogue.serve_fastening import example
    joint, _ = example()
    if a.size:
        joint = joint.modified(size=a.size)
    if a.stl:
        print(f"written {a.stl}: {export_stl(joint, a.stl)} triangles")
    if a.step:
        if a.engine == "ocp" and not cad_ocp.available():
            raise SystemExit("CAD 엔진(OCP)을 쓸 수 없습니다. --engine 을 빼면 추가 설치 없이 STEP을 냅니다.")
        print(f"written {a.step}: {export_step(joint, a.step, a.engine)} parts ({a.engine})")
    if not (a.step or a.stl):
        ap.error("--step 또는 --stl 가운데 하나는 주어야 한다")


if __name__ == "__main__":
    main()
