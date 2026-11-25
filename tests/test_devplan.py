"""정적 계획 검사: 잘못된 의존·참조·학습 요구가 통과하지 않게 한다."""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from cont.devplan import main, validate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def docs():
    return (yaml.safe_load((ROOT / "docs/integration_jobs.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((ROOT / "docs/model_readiness.yaml").read_text(encoding="utf-8")))


def test_repository_plan_and_cli(docs, capsys):
    assert validate(*docs, ROOT) == []
    assert main(["--root", str(ROOT)]) == 0
    output = capsys.readouterr().out
    assert "배정/실행 지시 아님" in output
    assert "검사하지 않았습니다" in output


@pytest.mark.parametrize("mutation, message", [
    (lambda p,m: p['jobs'].append(deepcopy(p['jobs'][0])), '중복 ID'),
    (lambda p,m: p['jobs'][0].update(depends_on=['UNKNOWN']), '없는 의존 작업'),
    (lambda p,m: p['jobs'][0].update(depends_on=['CT02']), '의존 순환'),
    (lambda p,m: p['jobs'][0].update(depends_on=['CT01']), '의존 순환'),
    (lambda p,m: p['jobs'][0].update(depends_on='CT02'), '문자열 목록'),
    (lambda p,m: p['jobs'][0].update(reuse_paths=['does-not-exist']), '경로 없음'),
    (lambda p,m: p['jobs'][0].update(reuse_paths=['../outside']), '저장소 밖 경로'),
    (lambda p,m: p['jobs'][0].update(implementation_steps=[]), 'implementation_steps'),
    (lambda p,m: p['jobs'][0]['implementation_steps'][0].update(id='CT01.02'), 'ID/순서'),
    (lambda p,m: p['jobs'][0]['implementation_steps'][0].update(check=''), 'check 누락'),
    (lambda p,m: p['jobs'][0].update(core_objectives=['C7']), '없는 핵심 목표'),
    (lambda p,m: p['jobs'][0].update(model_refs=['UNDEFINED']), '없는 모형 참조'),
    (lambda p,m: p['jobs'][0].update(model_refs=['LLM_CHAT']), '양방향 참조'),
    (lambda p,m: m['models'][0].update(job_refs=['UNKNOWN']), '없는 작업 참조'),
    (lambda p,m: m['models'].append(deepcopy(m['models'][0])), '중복 ID'),
    (lambda p,m: p['jobs'][20].update(new_training_required=True), '새 학습 불필요'),
    (lambda p,m: m['models'][7].update(new_training_required=True), '새 학습 불필요'),
    (lambda p,m: m['models'][7].update(runtime_acceptance='accepted'), '별도 증거'),
    (lambda p,m: p['jobs'][0].update(planning_state='ready', owner=None), 'owner'),
    (lambda p,m: p.update(schema_version=999), 'schema_version'),
])
def test_rejects_invalid_contract(docs, mutation, message):
    plan, models = docs
    mutation(plan, models)
    assert any(message in e for e in validate(plan, models, ROOT))


@pytest.mark.parametrize("plan, models", [(None, None), ([], {}), ({'jobs':[None]}, {'models':[1]})])
def test_malformed_documents_return_errors(plan, models):
    assert validate(plan, models, ROOT)


def test_read_failure_does_not_succeed(tmp_path, capsys):
    assert main(['--root', str(tmp_path)]) == 2
    assert '읽기 실패' in capsys.readouterr().out


def test_invalid_yaml_and_failed_validation(tmp_path, docs, capsys):
    folder = tmp_path / 'docs'
    folder.mkdir()
    (folder / 'integration_jobs.yaml').write_text('jobs: [', encoding='utf-8')
    assert main(['--root', str(tmp_path)]) == 2
    plan, models = docs
    (folder / 'integration_jobs.yaml').write_text(yaml.safe_dump(plan), encoding='utf-8')
    (folder / 'model_readiness.yaml').write_text(yaml.safe_dump(models), encoding='utf-8')
    assert main(['--root', str(tmp_path)]) == 1
    assert 'ERROR' in capsys.readouterr().out
