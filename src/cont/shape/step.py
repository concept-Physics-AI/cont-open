"""형상 명세 → STEP 파일을 CAD 엔진 없이 직접 쓴다 (ISO 10303-21, AP214).

부품 하나는 "원 또는 육각 윤곽을 z0~z1로 세운 기둥, 가운데 원 구멍은 선택"이다. 이 형상은 평면과 원통면만으로 되어 있어
경계 표현(B-rep)을 손으로 적을 수 있다: 꼭짓점 → 모서리(직선, 원호) → 면(평면, 원통면) → 닫힌 껍질 → 솔리드.
원은 꼭짓점 둘(0도, 180도)로 나눈 원호 두 개로 적는다. 원통면도 반쪽 둘로 나눠, 이음선 없는 면만 쓴다.

추가 설치가 없어 어디서나 된다. 대신 이 모양(동축 기둥)만 쓸 수 있다. 더 복잡한 형상은 CAD 엔진(cad_ocp.py)으로 낸다.
화면용으로 잘라 낸 각도(sweep)는 무시하고 온전한 부품을 낸다. 단위 mm. 부품마다 PRODUCT 하나이며 이름은 역할(영어 식별자)이다.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

from cont.shape.spec import Assembly, Part

T, F = ".T.", ".F."


def _num(x: float) -> str:
    """STEP의 실수 표기: 소수점이 꼭 있어야 한다."""
    s = f"{float(x):.12G}"
    if "E" in s:
        mant, exp = s.split("E")
        return (mant if "." in mant else mant + ".") + "E" + exp
    return s if "." in s else s + "."


class _Writer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> str:
        self.lines.append(text)
        return f"#{len(self.lines)}"

    def point(self, x: float, y: float, z: float) -> str:
        return self.add(f"CARTESIAN_POINT('',({_num(x)},{_num(y)},{_num(z)}))")

    def direction(self, x: float, y: float, z: float) -> str:
        return self.add(f"DIRECTION('',({_num(x)},{_num(y)},{_num(z)}))")

    def axis(self, origin: tuple[float, float, float], z: tuple[float, float, float], x: tuple[float, float, float]) -> str:
        return self.add(f"AXIS2_PLACEMENT_3D('',{self.point(*origin)},{self.direction(*z)},{self.direction(*x)})")

    def vertex(self, p: tuple[float, float, float]) -> str:
        return self.add(f"VERTEX_POINT('',{self.point(*p)})")

    def line_edge(self, v0: str, v1: str, p0: tuple[float, float, float], p1: tuple[float, float, float]) -> str:
        d = tuple(b - a for a, b in zip(p0, p1)); n = math.sqrt(sum(c * c for c in d))
        vec = self.add(f"VECTOR('',{self.direction(*(c / n for c in d))},1.)")
        return self.add(f"EDGE_CURVE('',{v0},{v1},{self.add(f'LINE({chr(39)}{chr(39)},{self.point(*p0)},{vec})')},{T})")

    def arc_edge(self, v0: str, v1: str, z: float, r: float) -> str:
        """z 높이의 반지름 r인 원에서, 축을 중심으로 반시계 방향으로 v0에서 v1까지."""
        circle = self.add(f"CIRCLE('',{self.axis((0, 0, z), (0, 0, 1), (1, 0, 0))},{_num(r)})")
        return self.add(f"EDGE_CURVE('',{v0},{v1},{circle},{T})")

    def loop(self, edges: list[tuple[str, str]]) -> str:
        oriented = ",".join(self.add(f"ORIENTED_EDGE('',*,*,{e},{sense})") for e, sense in edges)
        return self.add(f"EDGE_LOOP('',({oriented}))")

    def face(self, surface: str, outer: list[tuple[str, str]], inner: list[tuple[str, str]] | None = None, same_sense: str = T) -> str:
        bounds = [self.add(f"FACE_OUTER_BOUND('',{self.loop(outer)},{T})")]
        if inner:
            bounds.append(self.add(f"FACE_BOUND('',{self.loop(inner)},{T})"))
        return self.add(f"ADVANCED_FACE('',({','.join(bounds)}),{surface},{same_sense})")


def _rev(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """같은 고리를 반대 방향으로."""
    return [(e, F if s == T else T) for e, s in reversed(edges)]


class _Circle:
    """한 높이의 원: 꼭짓점 A(0도), B(180도)와 원호 둘 (A→B, B→A, 둘 다 반시계)."""

    def __init__(self, w: _Writer, z: float, r: float) -> None:
        self.pa, self.pb = (r, 0.0, z), (-r, 0.0, z)
        self.a, self.b = w.vertex(self.pa), w.vertex(self.pb)
        self.ab, self.ba = w.arc_edge(self.a, self.b, z, r), w.arc_edge(self.b, self.a, z, r)

    @property
    def ccw(self) -> list[tuple[str, str]]:
        return [(self.ab, T), (self.ba, T)]


def _wall(w: _Writer, part: Part, r: float, faces_outward: bool) -> tuple[_Circle, _Circle, list[str]]:
    """원통 벽 (반쪽 면 둘). faces_outward=False면 구멍 벽이라 면이 축을 향한다."""
    bot, top = _Circle(w, part.z0, r), _Circle(w, part.z1, r)
    up_a, up_b = w.line_edge(bot.a, top.a, bot.pa, top.pa), w.line_edge(bot.b, top.b, bot.pb, top.pb)
    surface = w.add(f"CYLINDRICAL_SURFACE('',{w.axis((0, 0, part.z0), (0, 0, 1), (1, 0, 0))},{_num(r)})")
    halves = [[(bot.ab, T), (up_b, T), (top.ab, F), (up_a, F)],        # +y 쪽 반
              [(bot.ba, T), (up_a, T), (top.ba, F), (up_b, F)]]        # -y 쪽 반
    faces = [w.face(surface, h if faces_outward else _rev(h), same_sense=T if faces_outward else F) for h in halves]
    return bot, top, faces


def _solid(w: _Writer, part: Part) -> str:
    faces: list[str] = []
    if part.profile == "circle":
        bot, top, side = _wall(w, part, part.outer / 2, True)
        faces += side
        outer_top, outer_bot = top.ccw, _rev(bot.ccw)
    else:
        r = part.outer / math.sqrt(3)                                   # 꼭짓점까지의 거리. 평면 하나가 +x를 향한다 (메시와 같은 방향)
        pts = [(r * math.cos(math.radians(30 + 60 * k)), r * math.sin(math.radians(30 + 60 * k))) for k in range(6)]
        pb = [(x, y, part.z0) for x, y in pts]; pt = [(x, y, part.z1) for x, y in pts]
        vb = [w.vertex(p) for p in pb]; vt = [w.vertex(p) for p in pt]
        eb = [w.line_edge(vb[k], vb[(k + 1) % 6], pb[k], pb[(k + 1) % 6]) for k in range(6)]
        et = [w.line_edge(vt[k], vt[(k + 1) % 6], pt[k], pt[(k + 1) % 6]) for k in range(6)]
        ev = [w.line_edge(vb[k], vt[k], pb[k], pt[k]) for k in range(6)]
        for k in range(6):
            j = (k + 1) % 6
            a = math.radians(60 * (k + 1))                              # 이 평면의 바깥 방향
            mid = ((pb[k][0] + pb[j][0]) / 2, (pb[k][1] + pb[j][1]) / 2, part.z0)
            plane = w.add(f"PLANE('',{w.axis(mid, (math.cos(a), math.sin(a), 0.0), (0, 0, 1))})")
            faces.append(w.face(plane, [(eb[k], T), (ev[j], T), (et[k], F), (ev[k], F)]))
        outer_top = [(e, T) for e in et]
        outer_bot = _rev([(e, T) for e in eb])
    inner_top = inner_bot = None
    if part.inner > 0:
        hb, ht, hole = _wall(w, part, part.inner / 2, False)
        faces += hole
        inner_top, inner_bot = _rev(ht.ccw), hb.ccw                     # 구멍 둘레는 바깥 둘레와 반대로 돈다
    top_plane = w.add(f"PLANE('',{w.axis((0, 0, part.z1), (0, 0, 1), (1, 0, 0))})")
    bot_plane = w.add(f"PLANE('',{w.axis((0, 0, part.z0), (0, 0, -1), (1, 0, 0))})")
    faces.append(w.face(top_plane, outer_top, inner_top))
    faces.append(w.face(bot_plane, outer_bot, inner_bot))
    shell = w.add(f"CLOSED_SHELL('',({','.join(faces)}))")
    return w.add(f"MANIFOLD_SOLID_BREP('{part.role}',{shell})")


def step_text(assembly: Assembly, timestamp: str | None = None) -> str:
    w = _Writer()
    app = w.add("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
    w.add(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,{app})")
    pctx = w.add(f"PRODUCT_CONTEXT('',{app},'mechanical')")
    dctx = w.add(f"PRODUCT_DEFINITION_CONTEXT('part definition',{app},'design')")
    length = w.add("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
    angle = w.add("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
    solid_angle = w.add("(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())")
    unc = w.add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),{length},'distance_accuracy_value','confusion accuracy')")
    ctx = w.add(f"(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({unc})) "
                f"GLOBAL_UNIT_ASSIGNED_CONTEXT(({length},{angle},{solid_angle})) REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY'))")
    for part in assembly.parts:
        brep = _solid(w, part)
        origin = w.axis((0, 0, 0), (0, 0, 1), (1, 0, 0))
        rep = w.add(f"ADVANCED_BREP_SHAPE_REPRESENTATION('{part.role}',({origin},{brep}),{ctx})")
        product = w.add(f"PRODUCT('{part.role}','{part.role}','',({pctx}))")
        w.add(f"PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,({product}))")
        formation = w.add(f"PRODUCT_DEFINITION_FORMATION('','',{product})")
        definition = w.add(f"PRODUCT_DEFINITION('design','',{formation},{dctx})")
        shape = w.add(f"PRODUCT_DEFINITION_SHAPE('','',{definition})")
        w.add(f"SHAPE_DEFINITION_REPRESENTATION({shape},{rep})")
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    name = "".join(c if c.isascii() and c not in "'\\" else "_" for c in assembly.name)
    head = ("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ConT shape export'),'2;1');\n"
            f"FILE_NAME('{name}','{stamp}',('ConT'),('Conception'),'cont.shape.step','ConT','');\n"
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\nENDSEC;\nDATA;\n")
    return head + "".join(f"#{i + 1}={line};\n" for i, line in enumerate(w.lines)) + "ENDSEC;\nEND-ISO-10303-21;\n"


def write_step(assembly: Assembly, path: str | Path) -> int:
    """STEP 파일로 쓴다. 쓴 부품 수를 돌려준다."""
    Path(path).write_text(step_text(assembly), encoding="ascii")
    return len(assembly.parts)
