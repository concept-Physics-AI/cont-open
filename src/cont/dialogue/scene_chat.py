"""장면 대화(P1·P2 ↔ Y9): 대화 한 마디를 계획으로 풀어 명세·카메라·속도·선택·이미지·저장 도구를 순서대로 실행한다.

- 계획은 LLM이 JSON으로 내고, `plan.parse/validate`를 통과한 등록 도구만 실행한다. 모양이 틀리면 아무것도 실행하지 않는다.
- 한 턴은 전부 반영되거나 전부 되돌려진다(중간 단계 실패 시 이번 요청의 변경을 모두 취소). 사용자에게 보이는 답은 도구 결과로 코드가 만든다.
  LLM은 답문을 쓰지 않는다. 물리 값을 계산하지 않는다.
- 상태: 명세·보기(카메라·단계 속도)·선택·재생 위치·이미지. 저장·재열기는 `service.project`를 쓴다(모델 재호출 없음).
- 요청마다 새 실행기를 쓴다(같은 계획을 나중에 다시 내도 이전 결과를 재사용하지 않는다).
- 이미 저장한 프로젝트에서는 계획을 실행하기 **전에** 요청 기록(`plan_store.save_request`)을 남기고, 요청이 끝나면(완료·되돌림) 지운다.
  실행 중 프로세스가 죽으면 기록이 남아, 다시 열 때 알리고(`pending()`) 사용자가 `resume_pending()`으로 같은 계획을 다시 실행하거나
  `discard_pending()`으로 버린다. 조용히 이어 가지 않는다. 장면의 변경은 저장 전까지 메모리에만 있으므로 이어 실행은 **모든 단계를** 다시 실행하며
  (끝난 단계를 건너뛰지 않는다), 열었을 때의 상태가 요청을 받던 때와 다르면(저장하지 않은 변경이 사라졌음) 거절한다.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from cont.dialogue.context import ContextLimits, build_messages, configured_limits
from cont.dialogue.plan import Executor, Plan, PlanError, Tool, parse, validate
from cont.dialogue.plan_store import StaleCheckpoint, clear_request, has_request, load_request, save_request
from cont.generation import Generator
from cont.objspec import (ObjectSpec, ObjectSpecError, Selection, SelectionError, SpecImage, ViewState, edit_selection, generate_image, select,
                          select_region)
from cont.objspec.scene import Timeline
from cont.service.project import open_project, save_conversation, save_project

SYSTEM_PROMPT = (
    "너는 장면 편집 계획기다. 사용자 요청을 등록된 도구 호출 계획으로만 답한다. 출력은 JSON 한 개 {\"steps\":[{\"id\":\"s1\",\"tool\":..,\"args\":{..},\"depends_on\":[..]}]}이고 다른 글은 쓰지 않는다. "
    "도구와 인자는 아래 목록에 있는 것만 쓴다. 단계는 '2'처럼 순번 문자열이나 단계 ID로 적는다. '방금 것'·'그 부품'은 현재 상태의 선택·이미지로 해석한다. "
    "부품을 고치려면 먼저 select_part나 select_region으로 선택하고 edit_part를 depends_on으로 잇는다. 요청에 없는 변경은 넣지 않는다. "
    "요청이 가리키는 부품이 상태로 하나로 정해지지 않으면(예: '유전층'은 아래·위 둘이다) 어느 쪽인지 추측하지 말고 {\"steps\":[]}를 답한다. "
    "edit_part의 changes 항목 이름은 name(이름), z0(아래면 높이), z1(윗면 높이), outer(바깥 반지름), inner(안쪽 반지름)만 쓴다. 다른 이름을 만들지 않는다. "
    "되돌리기·취소는 지원하지 않는다. 이전 값을 짐작해 되돌리는 계획을 만들지 말고 {\"steps\":[]}를 답한다(사용자가 새 값을 말하면 그 값으로 고친다). "
    "치수·물리 값을 지어내지 않는다. 요청에 값이 없으면 계획에 넣지 말고 {\"steps\":[]}를 답한다."
)

_EDITABLE = ("name", "z0", "z1", "outer", "inner")                        # 프롬프트의 changes 항목 이름. 시험이 select._FIELDS와 같은지 확인한다


def _first_json(raw: str) -> Any:
    """응답에서 첫 JSON 객체 하나만 읽는다. 뒤에 글이나 다른 객체가 붙어도 앞의 객체를 쓴다."""
    i = raw.find("{")
    if i < 0:
        raise ValueError("JSON 객체가 없습니다")
    obj, _ = json.JSONDecoder().raw_decode(raw[i:])
    return obj


@dataclass
class Turn:
    text: str
    kind: str                     # done | failed | refused
    reply: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "kind": self.kind, "reply": self.reply, "steps": [dict(s) for s in self.steps],
                "changes": list(self.changes), "request_id": self.request_id}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Turn":
        return cls(d["text"], d["kind"], d["reply"], [dict(s) for s in d.get("steps", [])], list(d.get("changes", [])), d.get("request_id", ""))


class SceneSession:
    def __init__(self, spec: ObjectSpec, generator: Generator, provider: Any | None = None, *, root: str | Path | None = None,
                 project_id: str = "", name: str = "", view: ViewState | None = None, selection: tuple[str, ...] = (),
                 playback_t: float = 0.0, saved_images: list[Any] | None = None, context_limits: ContextLimits | None = None,
                 llm_opts: Mapping[str, Any] | None = None):
        self.generator, self.provider = generator, provider
        self.llm_opts = dict(llm_opts or {})                             # 공급자 호출 옵션(예: temperature)
        self.root, self.project_id, self.name = Path(root) if root else None, project_id, name
        self.spec, self.view, self.selection, self.playback_t = spec, view or ViewState(), tuple(selection), float(playback_t)
        self.saved_images: list[Any] = list(saved_images or [])           # 저장된 이미지 (SavedImage)
        self.new_images: list[SpecImage] = []                             # 아직 저장하지 않은 이미지
        self.baseline = (spec, self.view)                                 # 비교 기준: 열었을 때 또는 마지막 저장 때 상태
        self.turns: list[Turn] = []
        self.open_problems: list[str] = []                                # 열 때 알려야 할 문제(이미지 없음, 대화 기록 읽기 실패 등)
        self.saved_revision = 0                                           # 마지막으로 저장·연 프로젝트 개정(저장 전이면 0)
        self.context_limits = context_limits or configured_limits()

    @classmethod
    def open(cls, root: str | Path, generator: Generator, provider: Any | None = None) -> "SceneSession":
        o = open_project(root)                                            # 모델을 부르지 않는다
        st = o.state
        s = cls(st.spec, generator, provider, root=root, project_id=o.project_id, name=o.name, view=st.view,
                selection=st.selection, playback_t=st.playback_t, saved_images=st.images)
        s.turns = [Turn.from_dict(d) for d in st.conversation]            # 저장된 대화 기록(다음 요청의 문맥으로 쓰인다)
        s.open_problems = list(o.problems)
        s.saved_revision = o.revision
        p = s.pending()
        if p:
            s.open_problems.append(f"중단된 요청이 있습니다: '{p['text'][:60]}'" + (f" (이어 갈 수 없음: {p['stale']})" if p["stale"] else " (이어 하려면 resume_pending, 버리려면 discard_pending)"))
        return s

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
            r = save_project(S.root, S.project_id, S.name or S.spec.name, S.spec, S.view, S.selection, S.playback_t, S.new_images,
                             conversation=[t.to_dict() for t in S.turns])
            S.saved_revision = r["revision"]
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
        if self._pending_dir() is not None and has_request(self._pending_dir()):
            return self._end(Turn(text, "refused", "중단된 요청이 남아 있어 새 요청을 받지 않았습니다. 이어 하려면 resume_pending, 버리려면 discard_pending을 쓰세요. 아무것도 실행하지 않았습니다."))
        try:
            raw = self.provider.complete(self._messages(text), **self.llm_opts).text
        except Exception as e:                                           # 공급자 오류는 요청 실패로 남기고 상태를 건드리지 않는다
            return self._end(Turn(text, "refused", f"공급자 호출에 실패했습니다({type(e).__name__}). 아무것도 실행하지 않았습니다."))
        try:
            plan = parse(_first_json(raw))
            if not plan.steps:
                return self._end(Turn(text, "refused", "요청을 실행 가능한 단계로 풀지 못했습니다(값이 빠졌거나 지원하지 않는 요청). 아무것도 실행하지 않았습니다."))
            tools = self.tools()
            validate(plan, tools)
        except (ValueError, PlanError) as e:
            return self._end(Turn(text, "refused", f"계획이 맞지 않아 실행하지 않았습니다: {str(e)[:150]}"))
        return self._run_plan(text, plan, tools)

    def select_from_screen(self, ids: list[str] | tuple[str, ...], spec_version: str) -> tuple[str, ...]:
        """3D 장면에서 사용자가 고른 부품(`s4d:select` 이벤트의 ids·spec_version)을 선택 상태로 받는다. 다음 대화의 "그 부품"이 이것을 가리킨다.
        화면이 보여 준 명세 version이 지금과 다르면(오래된 화면) 받지 않는다. 명세에 없는 부품이 섞여 있어도 받지 않는다. 빈 목록은 선택을 비운다."""
        if spec_version != self.spec.version:
            raise SelectionError("화면의 장면이 지금 명세와 다릅니다(오래된 화면). 선택하지 않았습니다. 화면을 다시 불러오세요")
        ids = tuple(dict.fromkeys(ids))
        unknown = [i for i in ids if i not in self.spec.part_ids]
        if unknown:
            raise SelectionError(f"명세에 없는 부품입니다: {unknown}. 선택하지 않았습니다")
        self.selection = ids
        return self.selection

    # ---- 중단된 요청 -----------------------------------------------------------------------------------------
    def _pending_dir(self) -> Path | None:
        """요청 기록을 둘 곳. 아직 저장한 적 없는 프로젝트는 다시 열 수 없으므로 기록하지 않는다."""
        return self.root / "pending" if self.root is not None and self.saved_revision > 0 else None

    def _fingerprint(self) -> dict[str, Any]:
        """요청을 받던 때의 장면 상태. 열었을 때 이것과 같아야 같은 계획을 이어 실행한다."""
        imgs = [i.rep_id for i in self.saved_images] + [f"new:{i.representation.id}" for i in self.new_images]
        state = {"spec_version": self.spec.version, "view": self.view.to_dict(), "selection": list(self.selection),
                 "playback_t": self.playback_t, "images": imgs}
        return {"project_id": self.project_id, "revision": self.saved_revision,
                "state_sha256": hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()}

    def pending(self) -> dict[str, Any] | None:
        """남아 있는 중단된 요청. 없으면 None. stale이 문자열이면 지금 상태로는 이어 갈 수 없는 이유다."""
        d = self._pending_dir()
        if d is None or not has_request(d):
            return None
        try:
            text, plan, ctx = load_request(d)
        except StaleCheckpoint as e:
            return {"text": "(읽을 수 없는 요청)", "request_id": "", "tools": [], "stale": str(e)}
        want, stale = self._fingerprint(), ""
        if ctx != want:
            diff = sorted(k for k in set(ctx) | set(want) if ctx.get(k) != want.get(k))
            stale = ("열었을 때 상태가 요청을 받던 때와 다릅니다(" + ", ".join(diff) + "). 저장하지 않은 변경이 사라졌을 수 있어 이어 가지 않습니다")
        else:
            try:
                validate(plan, self.tools())
            except PlanError as e:
                stale = f"지금의 도구로는 계획이 맞지 않습니다: {str(e)[:100]}"
        return {"text": text, "request_id": plan.request_id(), "tools": [s.tool for s in plan.steps], "stale": stale}

    def resume_pending(self) -> Turn:
        """중단된 요청의 계획을 같은 상태에서 처음부터 다시 실행한다(LLM을 다시 부르지 않는다). 이어 갈 수 없으면 아무것도 하지 않고 이유를 알린다."""
        p = self.pending()
        if p is None:
            return self._end(Turn("(이어 하기)", "refused", "이어 할 중단된 요청이 없습니다."))
        if p["stale"]:
            return self._end(Turn(p["text"], "refused", f"중단된 요청을 이어 가지 않았습니다: {p['stale']}. 버리려면 discard_pending을 쓰세요. 아무것도 실행하지 않았습니다."))
        text, plan, _ = load_request(self._pending_dir())
        t = self._run_plan(text, plan, self.tools(), resumed=True)
        return t

    def discard_pending(self) -> bool:
        d = self._pending_dir()
        return clear_request(d) if d is not None else False

    def _run_plan(self, text: str, plan: Plan, tools: dict[str, Tool], resumed: bool = False) -> Turn:
        d = self._pending_dir()
        if d is not None:
            try:
                save_request(d, text, plan, self._fingerprint())       # 실행 전에 남긴다. 못 남기면 실행하지 않는다
            except OSError as e:
                return self._end(Turn(text, "refused", f"중단에 대비한 요청 기록을 남기지 못해 실행하지 않았습니다({type(e).__name__}). 아무것도 실행하지 않았습니다."))
        snap = self._snapshot()
        run = Executor(tools).execute(plan)
        steps = [{"id": s.id, "tool": s.tool, "state": run.states[s.id].state, "error": run.states[s.id].error} for s in plan.steps]
        rid = plan.request_id()
        if run.done:
            lines = [str(run.states[s.id].result.get("summary", s.tool)) for s in plan.steps]       # type: ignore[union-attr]
            if d is not None:
                clear_request(d)
            return self._end(Turn(text, "done", ("중단된 요청을 이어 실행했습니다.\n" if resumed else "") + "\n".join(lines), steps, lines, rid))
        bad = next(s for s in plan.steps if run.states[s.id].state == "failed")
        self._restore(snap)
        if d is not None:
            clear_request(d)                                           # 실패해 전부 되돌렸으므로 이어 할 것이 없다
        return self._end(Turn(text, "failed", f"'{bad.tool}' 단계가 실패해 이번 요청의 변경을 모두 되돌렸습니다: {run.states[bad.id].error}", steps, [], rid))

    def _end(self, t: Turn) -> Turn:
        self.turns.append(t)
        if t.kind == "done" and self.root is not None and any(s["tool"] == "save_project" for s in t.steps):
            try:                                                         # 저장한 요청 자신까지 대화 기록에 넣는다(상태 저장은 이미 끝났다)
                save_conversation(self.root, self.project_id, [x.to_dict() for x in self.turns])
            except Exception as e:
                t.reply += f"\n(대화 기록을 저장하지 못했습니다: {type(e).__name__})"
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
