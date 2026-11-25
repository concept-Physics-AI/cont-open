"""개발 계획의 정적 정합성 검사. 작업 배정·실행·학습·인수는 하지 않는다."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def validate(plan: Any, readiness: Any, root: Path) -> list[str]:
    """계획/모형 명세의 구조·참조·경로를 검사하고 오류 목록을 반환한다."""
    errors: list[str] = []
    root = root.resolve()

    def fail(label: str, reason: str) -> None:
        errors.append(f"{label}: {reason}")

    def strings(value: Any, label: str, *, empty: bool = False) -> list[str]:
        if not isinstance(value, list) or (not empty and not value):
            fail(label, "문자열 목록이 필요합니다")
            return []
        if any(not isinstance(v, str) or not v.strip() for v in value):
            fail(label, "비어 있지 않은 문자열만 허용합니다")
            return []
        if len(value) != len(set(value)):
            fail(label, "중복 항목")
        return value

    def path_check(value: Any, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            fail(label, "저장소 상대 경로가 필요합니다")
            return
        path = root / value
        if Path(value).is_absolute() or not path.resolve().is_relative_to(root):
            fail(label, "저장소 밖 경로")
        elif not path.exists():
            fail(label, f"경로 없음: {value}")

    def records(doc: Any, field: str, kind: str, version: int) -> dict[str, dict]:
        if not isinstance(doc, dict):
            fail(field, "문서 객체가 필요합니다")
            return {}
        if doc.get("kind") != kind or doc.get("schema_version") != version:
            fail(field, "kind/schema_version 불일치")
        rows = doc.get(field)
        if not isinstance(rows, list) or not rows:
            fail(field, "비어 있지 않은 항목 목록이 필요합니다")
            return {}
        result = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
                fail(field, "항목에 문자열 id가 필요합니다")
                continue
            rid = row["id"]
            if rid in result:
                fail(rid, "중복 ID")
            result[rid] = row
        return result

    jobs = records(plan, "jobs", "development_plan_not_runtime_state", 2)
    models = records(readiness, "models", "model_readiness_plan_not_runtime_registry", 1)
    if not isinstance(plan, dict) or not isinstance(readiness, dict):
        return errors
    objectives = plan.get("core_objectives")
    if not isinstance(objectives, dict) or set(objectives) != {f"C{i}" for i in range(1, 7)}:
        fail("core_objectives", "C1~C6 정의가 필요합니다")
        objectives = {}
    for doc, fields in ((plan, ("definition_authority", "process_authority", "model_contracts")),
                        (readiness, ("process_authority",))):
        for field in fields:
            path_check(doc.get(field), field)
    edges: dict[str, list[str]] = {}
    job_models: dict[str, list[str]] = {}
    model_jobs: dict[str, list[str]] = {}
    for jid, job in jobs.items():
        for field in ("title", "owner_role", "rollback"):
            if not isinstance(job.get(field), str) or not job[field].strip():
                fail(jid, f"{field} 누락")
        if job.get("track") not in {"control", "generative", "physics", "acceptance"}:
            fail(jid, "잘못된 track")
        state = job.get("planning_state")
        if state not in {"planned", "ready", "in_progress", "implemented", "checked", "accepted", "blocked", "cancelled"}:
            fail(jid, "잘못된 planning_state")
        if state not in {"planned", "blocked", "cancelled"} and not job.get("owner"):
            fail(jid, "진행 상태에는 실제 owner가 필요합니다")
        if job.get("new_training_required") is not False:
            fail(jid, "현재 새 학습 불필요 계약 위반")
        for field in ("deliverables", "acceptance", "negative_tests", "evidence_required", "entry_requirements", "handoff_required"):
            strings(job.get(field), f"{jid}.{field}")
        for path in strings(job.get("reuse_paths"), f"{jid}.reuse_paths"):
            path_check(path, jid)
        goals = strings(job.get("core_objectives"), f"{jid}.core_objectives")
        for goal in goals:
            if goal not in objectives:
                fail(jid, f"없는 핵심 목표: {goal}")
        edges[jid] = strings(job.get("depends_on"), f"{jid}.depends_on", empty=True)
        for dep in edges[jid]:
            if dep not in jobs:
                fail(jid, f"없는 의존 작업: {dep}")
        job_models[jid] = strings(job.get("model_refs"), f"{jid}.model_refs", empty=True)
        for mid in job_models[jid]:
            if mid not in models:
                fail(jid, f"없는 모형 참조: {mid}")
        steps = job.get("implementation_steps")
        if not isinstance(steps, list) or not steps:
            fail(jid, "implementation_steps 누락")
            continue
        for i, step in enumerate(steps, 1):
            if not isinstance(step, dict) or step.get("id") != f"{jid}.{i:02d}":
                fail(jid, "세부 단계 ID/순서 불일치")
                continue
            for field in ("action", "output", "check"):
                if not isinstance(step.get(field), str) or not step[field].strip():
                    fail(step["id"], f"{field} 누락")

    for mid, model in models.items():
        for field in ("area", "kind", "role", "inputs", "outputs", "acceptance", "implementation_note", "failure_policy"):
            if not isinstance(model.get(field), str) or not model[field].strip():
                fail(mid, f"{field} 누락")
        if model.get("new_training_required") is not False:
            fail(mid, "현재 새 학습 불필요 계약 위반")
        if model.get("runtime_acceptance") != "pending":
            fail(mid, "이 준비 명세는 pending만 기록; 실제 인수는 별도 증거 기록")
        strings(model.get("evidence_required"), f"{mid}.evidence_required")
        for path in strings(model.get("reuse_paths"), f"{mid}.reuse_paths"):
            path_check(path, mid)
        if model.get("config_ref") is not None:
            path_check(model["config_ref"], mid)
        model_jobs[mid] = strings(model.get("job_refs"), f"{mid}.job_refs")
        for jid in model_jobs[mid]:
            if jid not in jobs:
                fail(mid, f"없는 작업 참조: {jid}")
            elif mid not in job_models[jid]:
                fail(mid, f"양방향 참조 불일치: {jid}")
    for jid, refs in job_models.items():
        for mid in refs:
            if mid in models and jid not in model_jobs[mid]:
                fail(jid, f"양방향 참조 불일치: {mid}")

    # Kahn's algorithm also rejects self-dependencies, without recursion depth limits.
    remaining = {jid: set(deps) & jobs.keys() for jid, deps in edges.items()}
    while remaining:
        roots = {jid for jid, deps in remaining.items() if not deps}
        if not roots:
            fail("depends_on", "의존 순환: " + ", ".join(sorted(remaining)))
            break
        remaining = {jid: deps - roots for jid, deps in remaining.items() if jid not in roots}
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트")
    args = parser.parse_args(argv)
    try:
        plan = yaml.safe_load((args.root / "docs/integration_jobs.yaml").read_text(encoding="utf-8"))
        readiness = yaml.safe_load((args.root / "docs/model_readiness.yaml").read_text(encoding="utf-8"))
        errors = validate(plan, readiness, args.root)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        print(f"계획 읽기 실패: {exc}")
        return 2
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    jobs = plan["jobs"]
    print(f"정적 계획 검사 통과: 작업 {len(jobs)}, 세부 단계 {sum(len(j['implementation_steps']) for j in jobs)}, 모형/연산자 {len(readiness['models'])}")
    print("계획상 시작 후보(배정/실행 지시 아님): " + ", ".join(j["id"] for j in jobs if not j["depends_on"]))
    print("실제 모델·브라우저·물리 정확도·담당 배정·증거 인수는 검사하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
