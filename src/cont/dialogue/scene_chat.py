"""장면 대화(P1·P2 ↔ Y9): 대화 한 마디를 계획으로 풀어 명세·카메라·속도·선택·이미지·저장 도구를 순서대로 실행한다.

- 계획은 LLM이 JSON으로 내고, `plan.parse/validate`를 통과한 등록 도구만 실행한다. 모양이 틀리면 아무것도 실행하지 않는다.
- 한 턴은 전부 반영되거나 전부 되돌려진다(중간 단계 실패 시 이번 요청의 변경을 모두 취소). 사용자에게 보이는 답은 도구 결과로 코드가 만든다.
  LLM은 답문을 쓰지 않는다. 물리 값을 계산하지 않는다.
- 상태: 명세·보기(카메라·단계 속도)·선택·재생 위치·이미지. 저장·재열기는 `service.project`를 쓴다(모델 재호출 없음).
- 요청마다 새 실행기를 쓴다(같은 계획을 나중에 다시 내도 이전 결과를 재사용하지 않는다).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from cont.dialogue.context import ContextLimits, build_messages, configured_limits
from cont.dialogue.plan import Executor, PlanError, Tool, parse, validate
from cont.generation import Generator
from cont.objspec import (ObjectSpec, ObjectSpecError, Selection, SpecImage, ViewState, edit_selection, generate_image, select,
                          select_region)
from cont.objspec.scene import Timeline
from cont.service.project import open_project, save_project

SYSTEM_PROMPT = (
    "너는 장면 편집 계획기다. 사용자 요청을 등록된 도구 호출 계획으로만 답한다. 출력은 JSON 한 개 {\"steps\":[{\"id\":\"s1\",\"tool\":..,\"args\":{..},\"depends_on\":[..]}]}이고 다른 글은 쓰지 않는다. "
    "도구와 인자는 아래 목록에 있는 것만 쓴다. 단계는 '2'처럼 순번 문자열이나 단계 ID로 적는다. '방금 것'·'그 부품'은 현재 상태의 선택·이미지로 해석한다. "
    "부품을 고치려면 먼저 select_part나 select_region으로 선택하고 edit_part를 depends_on으로 잇는다. 요청에 없는 변경은 넣지 않는다. "
    "치수·물리 값을 지어내지 않는다. 요청에 값이 없으면 계획에 넣지 말고 {\"steps\":[]}를 답한다."
)


@dataclass
class Turn:
    text: str
    kind: str                     # done | failed | refused
    reply: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    request_id: str = ""


class SceneSession:
    def __init__(self, spec: ObjectSpec, generator: Generator, provider: Any | None = None, *, root: str | Path | None = None,
                 project_id: str = "", name: str = "", view: ViewState | None = None, selection: tuple[str, ...] = (),
                 playback_t: float = 0.0, saved_images: list[Any] | None = None, context_limits: ContextLimits | None = None):
        self.generator, self.provider = generator, provider
        self.root, self.project_id, self.name = Path(root) if root else None, project_id, name
        self.spec, self.view, self.selection, self.playback_t = spec, view or ViewState(), tuple(selection), float(playback_t)
        self.saved_images: list[Any] = list(saved_images or [])           # 저장된 이미지 (SavedImage)
        self.new_images: list[SpecImage] = []                             # 아직 저장하지 않은 이미지
        self.baseline = (spec, self.view)                                 # 비교 기준: 열었을 때 또는 마지막 저장 때 상태
        self.turns: list[Turn] = []
        self.context_limits = context_limits or configured_limits()

    @classmethod
    def open(cls, root: str | Path, generator: Generator, provider: Any | None = None) -> "SceneSession":
        o = open_project(root)                                            # 모델을 부르지 않는다
        st = o.state
        return cls(st.spec, generator, provider, root=root, project_id=o.project_id, name=o.name, view=st.view,
                   selection=st.selection, playback_t=st.playback_t, saved_images=st.images)

    # ---- 상태 -------------------------------------------------------------------------------------------------
    def _snapshot(self) -> tuple[Any, ...]:
        return (self.spec, self.view, self.selection, self.playback_t, len(self.new_images), self.baseline, list(self.saved_images))

    def _restore(self, snap: tuple[Any, ...]) -> None:
        self.spec, self.view, self.selection, self.playback_t = snap[:4]
        del self.new_images[snap[4]:]
        self.baseline, self.saved_images = snap[5], snap[6]

    def duration(self) -> float:
        return Timeline(self.spec, self.view).duration

    def state_json(self) -> dict[str, Any]:
        last = (self.new_images[-1].record if self.new_images else (self.saved_images[-1].record if self.saved_images else None))
        lo = {"rep_id": (self.new_images[-1].representation.id if self.new_images else (self.saved_images[-1].rep_id if self.saved_images else None)),
              "stage": (last or {}).get("object_spec", {}).get("stage"), "real": (last or {}).get("real")} if last else None
        return {"domain": "scene", "name": self.spec.name, "dimension_status": self.spec.dimension_status,
                "parts": [{"id": p.id, "name": p.part.name, "layer": p.layer} for p in self.spec.parts],
                "stages": [{"n": i + 1, "id": s.id, "name": s.name, "speed": self.view.speed_of(s.id)} for i, s in enumerate(self.spec.stages)],
                "camera": {"azimuth": self.view.azimuth, "elevation": self.view.elevation, "distance": self.view.distance},
                "selection": list(self.selection), "playback_t": self.playback_t, "duration": self.duration(), "last_image": lo,
                "unsaved_images": len(self.new_images), "units": {"length": "mm", "angle": "deg", "time": "s(설명용)"}}

    # ---- 도구 -------------------------------------------------------------------------------------------------
    def tools(self) -> dict[str, Tool]:
        S = self

        def stage_ref(v: str) -> int | str:
            return int(v) if isinstance(v, str) and v.strip().isdigit() else v

        def select_part(ref: str) -> Mapping[str, Any]:
            sel = select(S.spec, ref)
            S.selection = sel.parts
            return {"summary": f"선택: {', '.join(S.spec.part(p).part.name for p in sel.parts)}", "parts": list(sel.parts)}

        def select_reg(rect: list) -> Mapping[str, Any]:
            if len(rect) != 4 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in rect):
                raise ObjectSpecError("영역은 숫자 네 개 [x0, y0, x1, y1]이어야 합니다")
            sel = select_region(S.spec, tuple(float(x) for x in rect))
            S.selection = sel.parts
            return {"summary": f"영역 선택: {', '.join(S.spec.part(p).part.name for p in sel.parts)}", "parts": list(sel.parts)}

        def edit_part(changes: dict) -> Mapping[str, Any]:
            if not S.selection:
                raise ObjectSpecError("고칠 부품이 선택되어 있지 않습니다")
            r = edit_selection(S.spec, Selection(S.selection, "id"), **changes)
            if not r.changed:
                raise ObjectSpecError("같은 값이라 바뀐 것이 없습니다")
            S.spec = r.new
            lines = [f"{S.spec.part(p).part.name}: " + ", ".join(f"{k} {a}→{b}" for k, (a, b) in d.items()) for p, d in r.diff.items()]
            return {"summary": "부품 수정 — " + "; ".join(lines), "changed": list(r.changed), "kept": list(r.unchanged)}

        def edit_stage_pose(stage: str, part: str, changes: dict) -> Mapping[str, Any]:
            before = S.spec.stage(stage_ref(stage)).pose_of(part)
            S.spec = S.spec.edit_stage_pose(stage_ref(stage), part, **changes)
            after = S.spec.stage(stage_ref(stage)).pose_of(part)
            return {"summary": f"{S.spec.stage(stage_ref(stage)).name} 단계의 {S.spec.part(part).part.name} 자세 dz {before.dz}→{after.dz}, dx {before.dx}→{after.dx}"}

        def set_speed(stage: str, factor: (int, float)) -> Mapping[str, Any]:
            st = S.spec.stage(stage_ref(stage))
            old = S.duration()
            S.view = S.view.with_speed(S.spec, st.id, float(factor))
            S.playback_t = min(S.playback_t, S.duration())
            return {"summary": f"{st.name} 단계 재생 속도 {float(factor)}배 (전체 설명용 재생 {old:.1f}s → {S.duration():.1f}s)"}

        def set_camera(azimuth: (int, float) = None, elevation: (int, float) = None, distance: (int, float) = None) -> Mapping[str, Any]:
            kw = {k: float(v) for k, v in (("azimuth", azimuth), ("elevation", elevation), ("distance", distance)) if v is not None}
            if not kw:
                raise ObjectSpecError("바꿀 카메라 값이 없습니다")
            S.view = S.view.with_camera(**kw)
            return {"summary": "카메라 " + ", ".join(f"{k} {v}" for k, v in kw.items()) + " (장면 구조는 그대로)"}

        def seek(t: (int, float)) -> Mapping[str, Any]:
            if not 0 <= t <= S.duration() + 1e-9:
                raise ObjectSpecError(f"재생 위치는 0~{S.duration():.1f}초 사이여야 합니다")
            S.playback_t = float(t)
            return {"summary": f"재생 위치 {float(t):.1f}초"}

        def make_image(stage: str = "", seed: int = 0, size: int = 1024) -> Mapping[str, Any]:
            img = generate_image(S.spec, S.generator, stage_ref(stage) if stage else None, rep_id=f"image{len(S.saved_images) + len(S.new_images) + 1}",
                                 seed=seed, width=size, height=size)
            S.new_images.append(img)
            real = img.record["real"]
            return {"summary": f"설명 이미지 생성({'실제 모델' if real else '가짜 생성기, 실제 생성 아님'}: {img.record['model']})", "real": real,
                    "sha256": img.record["sha256"], "rep_id": img.representation.id}

        def compare() -> Mapping[str, Any]:
            lines = diff_lines(*S.baseline, S.spec, S.view)
            return {"summary": "기준(열었을 때 또는 마지막 저장)과 비교: " + ("; ".join(lines) if lines else "달라진 것이 없습니다"), "diff": lines}

        def save() -> Mapping[str, Any]:
            if S.root is None or not S.project_id:
                raise RuntimeError("저장할 프로젝트 폴더가 정해지지 않았습니다")
            r = save_project(S.root, S.project_id, S.name or S.spec.name, S.spec, S.view, S.selection, S.playback_t, S.new_images)
            S.saved_images = open_project(S.root).state.images
            S.new_images = []
            S.baseline = (S.spec, S.view)
            return {"summary": f"저장했습니다 (개정 {r['revision']}, 이미지 {r['images']}개)", "revision": r["revision"]}

        T = Tool
        return {"select_part": T("select_part", select_part, {"ref": str}),
                "select_region": T("select_region", select_reg, {"rect": list}),
                "edit_part": T("edit_part", edit_part, {"changes": dict}),
                "edit_stage_pose": T("edit_stage_pose", edit_stage_pose, {"stage": str, "part": str, "changes": dict}),
                "set_stage_speed": T("set_stage_speed", set_speed, {"stage": str, "factor": (int, float)}),
                "set_camera": T("set_camera", set_camera, {}, {"azimuth": (int, float), "elevation": (int, float), "distance": (int, float)}),
                "seek": T("seek", seek, {"t": (int, float)}),
                "make_image": T("make_image", make_image, {}, {"stage": str, "seed": int, "size": int}),
                "compare": T("compare", compare, {}),
                "save_project": T("save_project", save, {})}

    # ---- 대화 -------------------------------------------------------------------------------------------------
    def _catalog(self) -> str:
        def nm(t: Any) -> str:
            return "/".join(x.__name__ for x in (t if isinstance(t, tuple) else (t,)))
        rows = []
        for n, t in self.tools().items():
            a = ", ".join([f"{k}:{nm(v)}" for k, v in t.args.items()] + [f"{k}?:{nm(v)}" for k, v in t.optional.items()])
            rows.append(f"- {n}({a})")
        return "도구 목록:\n" + "\n".join(rows)

    def _messages(self, text: str) -> list[Any]:
        state = ("현재 상태(JSON)는 실제 적용된 값이다. 과거 실패한 요청은 적용되지 않았다.\n" + self._catalog() + "\n"
                 + json.dumps(self.state_json(), ensure_ascii=False, allow_nan=False))
        history = [(t.text, json.dumps({"outcome": t.kind, "changes": t.changes}, ensure_ascii=False)) for t in self.turns[-self.context_limits.history_turns:]] \
            if self.context_limits.history_turns else []
        return build_messages(SYSTEM_PROMPT, state, history, text, self.context_limits)

    def turn(self, text: str) -> Turn:
        if self.provider is None:
            return self._end(Turn(text, "refused", "계획을 만들 LLM 공급자가 연결되어 있지 않습니다. 아무것도 실행하지 않았습니다."))
        try:
            raw = self.provider.complete(self._messages(text)).text
        except Exception as e:                                           # 공급자 오류는 요청 실패로 남기고 상태를 건드리지 않는다
            return self._end(Turn(text, "refused", f"공급자 호출에 실패했습니다({type(e).__name__}). 아무것도 실행하지 않았습니다."))
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            plan = parse(json.loads(m.group(0) if m else ""))
            if not plan.steps:
                return self._end(Turn(text, "refused", "요청을 실행 가능한 단계로 풀지 못했습니다(값이 빠졌거나 지원하지 않는 요청). 아무것도 실행하지 않았습니다."))
            tools = self.tools()
            validate(plan, tools)
        except (ValueError, PlanError) as e:
            return self._end(Turn(text, "refused", f"계획이 맞지 않아 실행하지 않았습니다: {str(e)[:150]}"))
        snap = self._snapshot()
        run = Executor(tools).execute(plan)
        steps = [{"id": s.id, "tool": s.tool, "state": run.states[s.id].state, "error": run.states[s.id].error} for s in plan.steps]
        rid = plan.request_id()
        if run.done:
            lines = [str(run.states[s.id].result.get("summary", s.tool)) for s in plan.steps]       # type: ignore[union-attr]
            return self._end(Turn(text, "done", "\n".join(lines), steps, lines, rid))
        bad = next(s for s in plan.steps if run.states[s.id].state == "failed")
        self._restore(snap)
        return self._end(Turn(text, "failed", f"'{bad.tool}' 단계가 실패해 이번 요청의 변경을 모두 되돌렸습니다: {run.states[bad.id].error}", steps, [], rid))

    def _end(self, t: Turn) -> Turn:
        self.turns.append(t)
        return t


def diff_lines(old_spec: ObjectSpec, old_view: ViewState, new_spec: ObjectSpec, new_view: ViewState) -> list[str]:
    out: list[str] = []
    for pid in new_spec.part_ids:
        if pid not in old_spec.part_ids:
            out.append(f"부품 추가: {pid}")
            continue
        a, b = old_spec.part(pid).part, new_spec.part(pid).part
        ch = [f"{f} {getattr(a, f)}→{getattr(b, f)}" for f in ("name", "z0", "z1", "outer", "inner") if getattr(a, f) != getattr(b, f)]
        if ch:
            out.append(f"{b.name}: " + ", ".join(ch))
    for st in new_spec.stages:
        old = next((s for s in old_spec.stages if s.id == st.id), None)
        for pid, pose in st.poses:
            op = old.pose_of(pid) if old else None
            if op is not None and (op.dz, op.dx) != (pose.dz, pose.dx):
                out.append(f"{st.name} 단계 {new_spec.part(pid).part.name} 자세 dz {op.dz}→{pose.dz}, dx {op.dx}→{pose.dx}")
    for st in new_spec.stages:
        a, b = old_view.speed_of(st.id), new_view.speed_of(st.id)
        if a != b:
            out.append(f"{st.name} 단계 속도 {a}배→{b}배")
    for f in ("azimuth", "elevation", "distance"):
        a, b = getattr(old_view, f), getattr(new_view, f)
        if a != b:
            out.append(f"카메라 {f} {a}→{b}")
    return out
