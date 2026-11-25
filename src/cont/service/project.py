"""프로젝트 저장·재열기 (P6): 대상 명세, 보기 상태(카메라·단계 속도), 선택, 재생 위치, 이미지 기록을 한 폴더에 저장하고
다시 열어 같은 상태로 복원한다. 모델은 다시 부르지 않는다. 저장한 파일만 읽는다.

- 명세·이미지는 기존 자료 장부(`service.ledger`)로 등록한다: 명세는 원본(source)이고 고친 명세는 이전 명세를 부모로 둔 파생물,
  이미지는 만든 때의 명세를 부모로 둔 파생물이다. ID·지문·프로젝트 경계는 장부 규칙을 그대로 따른다.
- manifest.json은 임시 파일에 쓴 뒤 바꿔 넣는다(원자적). 바꾸기 전 manifest는 manifest.prev.json에 남는다. 본문 해시가 맞지 않으면
  (손상·손으로 고침) 직전 정상 manifest로 열고 `recovered_from_previous`로 알린다. 파일이 없거나 바뀌었으면 숨기지 않고 `problems`에 적는다.
- 저장 폴더는 저장소 밖에 둔다. 원본을 덮어쓰지 않고, 이전 명세 version은 `restore_version`으로 다시 꺼낼 수 있다.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cont.objspec import ObjectSpec, ObjectSpecError, SpecImage, ViewState
from cont.objspec.scene import CONFIG_DIR, Timeline
from cont.service.ledger import Ledger, LedgerError, sha256_bytes

SCHEMA = 1
MANIFEST, PREV, LOCK = "manifest.json", "manifest.prev.json", ".lock"


class ProjectError(ValueError):
    pass


@dataclass
class SavedImage:
    rep_id: str
    art_id: str
    spec_version: str
    stage: str | None
    record: dict[str, Any]
    png: bytes | None            # 파일이 없거나 바뀌었으면 None
    status: str = "ok"           # ok | missing | changed


@dataclass
class ProjectState:
    spec: ObjectSpec
    view: ViewState = field(default_factory=ViewState)
    selection: tuple[str, ...] = ()              # 선택한 부품 ID
    playback_t: float = 0.0                      # 설명용 재생 위치(초)
    images: list[SavedImage] = field(default_factory=list)


@dataclass
class Opened:
    project_id: str
    name: str
    revision: int
    state: ProjectState
    history: list[dict[str, Any]]                # 저장된 명세 version들 (오래된 것부터)
    recovered_from_previous: bool = False
    problems: list[str] = field(default_factory=list)


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _lock_stale(config_dir: Path | None = None) -> float:
    with open((config_dir or CONFIG_DIR) / "objspec" / "project.yaml", encoding="utf-8") as fh:
        v = (yaml.safe_load(fh) or {}).get("lock_stale_seconds", 60)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise ProjectError(f"lock_stale_seconds={v!r}: 0보다 큰 수여야 합니다")
    return float(v)


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class _Lock:
    def __init__(self, root: Path, stale: float):
        self.path, self.stale = root / LOCK, stale

    def __enter__(self) -> "_Lock":
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode()); os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()                       # 죽은 저장의 잠금
                        continue
                except FileNotFoundError:
                    continue
                raise ProjectError("다른 저장이 진행 중입니다. 끝난 뒤 다시 저장하세요") from None
        raise ProjectError("저장 잠금을 얻지 못했습니다")

    def __exit__(self, *exc: object) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"{path.name}이 없습니다") from None
    except (ValueError, UnicodeError):
        raise ProjectError(f"{path.name}이 깨졌습니다") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("body"), dict):
        raise ProjectError(f"{path.name}의 형식이 맞지 않습니다")
    if raw.get("body_sha256") != sha256_bytes(_canon(raw["body"])):
        raise ProjectError(f"{path.name}의 내용이 해시와 맞지 않습니다 (손상되었거나 손으로 고침)")
    sv = raw["body"].get("schema_version")
    if sv != SCHEMA:
        raise ProjectError(f"지원하지 않는 저장 형식 버전입니다: {sv!r} (지원: {SCHEMA})")
    return raw["body"]


def _verified_spec(root: Path, ledger: Ledger, project_id: str, art: str, version: str, parent_version: str = "") -> ObjectSpec:
    try:
        rec = ledger.get(art)
    except LedgerError as e:
        raise ProjectError(f"명세 기록을 쓸 수 없습니다: {e}") from None
    if rec["project_id"] != project_id:
        raise ProjectError(f"다른 프로젝트의 명세 기록입니다: {art}")
    f = root / "files" / f"{art}.spec.json"
    try:
        data = f.read_bytes()
    except FileNotFoundError:
        raise ProjectError(f"명세 파일이 없습니다: {f.name}") from None
    try:
        ledger.check_content(art, data)
        spec = ObjectSpec.from_dict(json.loads(data.decode("utf-8")), parent_version)
    except (LedgerError, ObjectSpecError, ValueError) as e:
        raise ProjectError(f"명세를 열 수 없습니다: {e}") from None
    if spec.version != version:
        raise ProjectError("명세의 version이 기록과 다릅니다")
    return spec


def save_project(root: str | Path, project_id: str, name: str, spec: ObjectSpec, view: ViewState | None = None,
                 selection: tuple[str, ...] = (), playback_t: float = 0.0, images: list[SpecImage] | tuple[SpecImage, ...] = (),
                 config_dir: Path | None = None) -> dict[str, Any]:
    """현재 상태를 저장한다. 같은 명세 version이면 다시 쓰지 않고, 다르면 이전 명세를 부모로 새 version을 더한다."""
    if not isinstance(project_id, str) or not project_id.strip():
        raise ProjectError("프로젝트 ID가 필요합니다")
    view = view or ViewState()
    unknown = [p for p in selection if p not in spec.part_ids]
    if unknown:
        raise ProjectError(f"선택에 명세에 없는 부품이 있습니다: {unknown}")
    dur = Timeline(spec, view, config_dir=config_dir).duration if spec.stages else 0.0
    if isinstance(playback_t, bool) or not isinstance(playback_t, (int, float)) or not 0 <= playback_t <= dur + 1e-9:
        raise ProjectError(f"재생 위치 {playback_t!r}: 0~{dur}초 사이여야 합니다")
    root = Path(root)
    (root / "files").mkdir(parents=True, exist_ok=True)
    with _Lock(root, _lock_stale(config_dir)):
        ledger = Ledger(root / "ledger")
        old: dict[str, Any] | None = None
        if (root / MANIFEST).exists():
            try:
                old = _read_manifest(root / MANIFEST)
            except ProjectError:
                old = _read_manifest(root / PREV)            # 현재 것이 깨졌으면 직전 정상 manifest 위에 이어 쓴다
            if old["project_id"] != project_id:
                raise ProjectError(f"이 폴더는 다른 프로젝트({old['project_id']})의 것입니다")
        history: list[dict[str, Any]] = list(old["history"]) if old else []
        by_version = {h["version"]: h for h in history}
        # 명세
        if spec.version in by_version:
            cur = by_version[spec.version]
        else:
            data = _canon(spec.to_dict())
            parent_art = old["current"]["art"] if old else None
            rec = ledger.register("derived" if parent_art else "source", data, project_id, (parent_art,) if parent_art else (), f"spec {spec.version[:8]}")
            f = root / "files" / f"{rec['id']}.spec.json"
            if not f.exists():
                _atomic_write(f, data)
            cur = {"art": rec["id"], "version": spec.version, "parent_art": parent_art,
                   "parent_version": old["current"]["version"] if old else ""}
            history.append(cur)
            by_version[spec.version] = cur
        # 이미지: 이미 저장한 것은 그대로, 새 것만 더한다
        imgs: list[dict[str, Any]] = list(old["images"]) if old else []
        have = {i["art"] for i in imgs}
        for si in images:
            link = si.record.get("object_spec") or {}
            ver = link.get("spec_version")
            if ver not in by_version:
                raise ProjectError("이미지가 저장되지 않은 명세 version으로 만들어졌습니다. 그 명세를 먼저 저장하세요")
            png = si.result.png
            rec = ledger.register("derived", png, project_id, (by_version[ver]["art"],), f"image {si.representation.id}")
            f = root / "files" / f"{rec['id']}.png"
            if not f.exists():
                _atomic_write(f, png)
            if rec["id"] not in have:
                imgs.append({"art": rec["id"], "rep_id": si.representation.id, "spec_version": ver, "stage": link.get("stage"),
                             "record": dict(si.record)})
                have.add(rec["id"])
        body = {"schema_version": SCHEMA, "project_id": project_id, "name": name, "revision": (old["revision"] + 1) if old else 1,
                "current": {"art": cur["art"], "version": spec.version}, "history": history, "view": view.to_dict(),
                "selection": list(selection), "playback_t": float(playback_t), "images": imgs}
        out = {"body": body, "body_sha256": sha256_bytes(_canon(body))}
        mp = root / MANIFEST
        if mp.exists():
            tmp = root / (PREV + ".tmp")
            shutil.copyfile(mp, tmp)
            os.replace(tmp, root / PREV)                       # 바꾸기 전 manifest를 남긴다
        _atomic_write(mp, json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8"))
        return {"revision": body["revision"], "spec_art": cur["art"], "spec_version": spec.version, "images": len(imgs)}


def open_project(root: str | Path) -> Opened:
    """저장한 프로젝트를 연다. 모델을 부르지 않고 파일만 읽는다. 명세가 없거나 바뀌었으면 열지 않고,
    이미지가 없거나 바뀌었으면 열되 problems에 적는다."""
    root = Path(root)
    recovered, problems = False, []
    try:
        body = _read_manifest(root / MANIFEST)
    except ProjectError as first:
        if not (root / MANIFEST).exists() and not (root / PREV).exists():
            raise ProjectError(f"저장된 프로젝트가 없습니다: {root.name}") from None
        if "지원하지 않는 저장 형식" in str(first):
            raise
        try:
            body = _read_manifest(root / PREV)
        except ProjectError:
            raise ProjectError(f"manifest를 읽을 수 없고 직전 저장도 없습니다 ({first})") from None
        recovered = True
        problems.append(f"현재 manifest를 쓸 수 없어 직전 저장으로 열었습니다 ({first})")
    pid = body["project_id"]
    ledger = Ledger(root / "ledger")
    cur = body["current"]
    hist = {h["version"]: h for h in body["history"]}
    h = hist.get(cur["version"])
    if h is None or h["art"] != cur["art"]:
        raise ProjectError("manifest의 현재 명세가 이력과 맞지 않습니다")
    spec = _verified_spec(root, ledger, pid, cur["art"], cur["version"], h.get("parent_version", ""))
    try:
        view = ViewState.from_dict(body["view"])
    except ObjectSpecError as e:
        raise ProjectError(str(e)) from None
    sel = tuple(body.get("selection", []))
    if any(p not in spec.part_ids for p in sel):
        raise ProjectError("저장된 선택이 명세에 없는 부품을 가리킵니다")
    images: list[SavedImage] = []
    for im in body["images"]:
        png, status = None, "ok"
        try:
            rec = ledger.get(im["art"])
            if rec["project_id"] != pid:
                raise ProjectError(f"다른 프로젝트의 이미지 기록입니다: {im['art']}")
            png = (root / "files" / f"{im['art']}.png").read_bytes()
            ledger.check_content(im["art"], png)
        except FileNotFoundError:
            png, status = None, "missing"
            problems.append(f"이미지 파일이 없습니다: {im['rep_id']}")
        except LedgerError as e:
            png, status = None, "changed" if "다릅니다" in str(e) else "missing"
            problems.append(f"이미지를 쓸 수 없습니다 ({im['rep_id']}): {e}")
        images.append(SavedImage(im["rep_id"], im["art"], im["spec_version"], im.get("stage"), im["record"], png, status))
    return Opened(pid, body["name"], body["revision"], ProjectState(spec, view, sel, float(body["playback_t"]), images),
                  list(body["history"]), recovered, problems)


def restore_version(root: str | Path, spec_version: str) -> ObjectSpec:
    """이력에 있는 이전 명세 version을 꺼낸다. 현재 상태는 바꾸지 않는다(다시 저장해야 현재가 된다)."""
    root = Path(root)
    body = open_project(root)
    h = next((x for x in body.history if x["version"] == spec_version), None)
    if h is None:
        raise ProjectError(f"이력에 없는 명세 version입니다: {spec_version[:12]}")
    return _verified_spec(root, Ledger(root / "ledger"), body.project_id, h["art"], h["version"], h.get("parent_version", ""))
