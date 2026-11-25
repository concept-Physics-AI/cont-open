"""단계 재생 타임라인: 명세의 공정 단계를 설명용 재생 시간으로 펴고, 시각 t의 부품 자세를 구한다.

재생 시간은 설명용이다. 측정 시간이나 계산한 물리 시간이 아니다. 단계 속도를 바꾸면 그 단계의 길이만 바뀐다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .spec import ObjectSpec, ObjectSpecError, Pose, ViewState

CONFIG_DIR = Path(os.environ.get("CONT_CONFIG_DIR", Path(__file__).resolve().parents[3] / "config"))
EASES = ("linear", "smoothstep")


def load_playback(config_dir: Path | None = None) -> dict[str, Any]:
    f = (config_dir or CONFIG_DIR) / "objspec" / "playback.yaml"
    with open(f, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    base, ease = cfg.get("stage_base_seconds"), cfg.get("ease", "smoothstep")
    if isinstance(base, bool) or not isinstance(base, (int, float)) or base <= 0:
        raise ObjectSpecError(f"stage_base_seconds={base!r}: 0보다 큰 수여야 합니다 ({f.name})")
    if ease not in EASES:
        raise ObjectSpecError(f"ease='{ease}': {EASES} 중 하나여야 합니다")
    return {"stage_base_seconds": float(base), "ease": ease}


def _ease(u: float, kind: str) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u) if kind == "smoothstep" else u


@dataclass(frozen=True)
class Segment:
    stage_id: str
    name: str
    t0: float
    t1: float
    speed: float


class Timeline:
    def __init__(self, spec: ObjectSpec, view: ViewState | None = None, config_dir: Path | None = None):
        if not spec.stages:
            raise ObjectSpecError("재생할 단계가 없습니다")
        self.spec, self.view = spec, view or ViewState()
        cfg = load_playback(config_dir)
        self.base, self.ease = cfg["stage_base_seconds"], cfg["ease"]
        t, segs = 0.0, []
        for st in spec.stages:
            sp = self.view.speed_of(st.id)
            dur = self.base / sp
            segs.append(Segment(st.id, st.name, t, t + dur, sp))
            t += dur
        self.segments: tuple[Segment, ...] = tuple(segs)
        self.duration = t

    def _poses(self, index: int) -> dict[str, Pose]:
        """index번째 단계가 끝났을 때의 자세. -1은 시작 자세."""
        src = dict(self.spec.start) if index < 0 else dict(self.spec.stages[index].poses)
        return {pid: src.get(pid, Pose()) for pid in self.spec.part_ids}

    def segment_at(self, t: float) -> Segment:
        """t가 속한 단계. 경계 시각은 뒤 단계에 속하고, 끝 시각은 마지막 단계에 속한다."""
        t = min(max(t, 0.0), self.duration)
        for seg in self.segments[:-1]:
            if t < seg.t1:
                return seg
        return self.segments[-1]

    def pose_at(self, t: float) -> dict[str, Pose]:
        t = min(max(t, 0.0), self.duration)
        i = next(k for k, sg in enumerate(self.segments) if t <= sg.t1)
        seg = self.segments[i]
        a, b = self._poses(i - 1), self._poses(i)
        u = _ease((t - seg.t0) / (seg.t1 - seg.t0), self.ease)
        return {pid: Pose(a[pid].dz + (b[pid].dz - a[pid].dz) * u, a[pid].dx + (b[pid].dx - a[pid].dx) * u)
                for pid in self.spec.part_ids}

    def to_dict(self) -> dict[str, Any]:
        """보기(JS)에 넘기는 값. 같은 식을 JS가 다시 계산한다."""
        return {
            "ease": self.ease, "duration": self.duration, "time_axis": self.spec.time_axis,
            "part_ids": list(self.spec.part_ids),
            "start": {pid: [p.dz, p.dx] for pid, p in self._poses(-1).items()},
            "segments": [{"id": sg.stage_id, "name": sg.name, "t0": sg.t0, "t1": sg.t1, "speed": sg.speed,
                          "end": {pid: [p.dz, p.dx] for pid, p in self._poses(k).items()}}
                         for k, sg in enumerate(self.segments)],
        }
