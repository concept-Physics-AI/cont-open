"""형상 명세 → STL 파일 (삼각형 메시). 추가 설치 없이 된다.

STL은 면으로만 된 형상이라 3D 프린터·보기 프로그램용이다. CAD에서 고칠 수 있는 형상은 STEP으로 낸다 (cad_ocp.py).
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from cont.shape.mesh import SEGMENTS, assembly_mesh
from cont.shape.spec import Assembly


def write_stl(assembly: Assembly, path: str | Path, segments: int = SEGMENTS) -> int:
    """이진 STL로 쓴다. 쓴 삼각형 수를 돌려준다. 모든 부품이 한 파일에 들어간다 (단위 mm)."""
    tris = np.concatenate([m.vertices[m.faces] for _, m in assembly_mesh(assembly, segments)])
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.where(length == 0, 1.0, length)
    header = b"ConT shape export (binary STL, mm)".ljust(80, b" ")
    with open(path, "wb") as f:
        f.write(header); f.write(struct.pack("<I", len(tris)))
        for normal, tri in zip(n, tris):
            f.write(struct.pack("<12fH", *normal, *tri.reshape(-1), 0))
    return len(tris)


def read_stl(path: str | Path) -> np.ndarray:
    """이진 STL의 삼각형 좌표 (M, 3, 3). 내보낸 파일을 확인하는 데 쓴다."""
    data = Path(path).read_bytes()
    (count,) = struct.unpack_from("<I", data, 80)
    rec = np.frombuffer(data, dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]), count=count, offset=84)
    return rec["v"].reshape(-1, 3, 3).astype(float)
