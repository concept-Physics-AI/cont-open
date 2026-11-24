"""정상 해시가 있어도 다른 실행의 파일이면 거부하며 경쟁 저장은 덮어쓰지 않는다."""
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cont.service import runs

ONE = "run-000000000001"
TWO = "run-000000000002"


def test_valid_record_copied_to_another_run_name_is_rejected(tmp_path):
    store = runs.RunStore(tmp_path)
    store.save({"run_id": ONE, "status": "complete"})
    shutil.copyfile(tmp_path / f"{ONE}.json", tmp_path / f"{TWO}.json")
    with pytest.raises(runs.RunCorrupt, match="식별자"):
        store.get(TWO)
    assert {r["run_id"]: r["status"] for r in store.list()} == {ONE: "complete", TWO: "corrupt"}


@pytest.mark.parametrize("body", ["[]", "null", "1", '"text"', "{broken", '{"run_id":"other"}'])
def test_invalid_record_is_reported_as_corrupt(tmp_path, body):
    (tmp_path / f"{ONE}.json").write_text(body, encoding="utf-8")
    store = runs.RunStore(tmp_path)
    with pytest.raises(runs.RunCorrupt):
        store.get(ONE)
    assert store.list() == [{"run_id": ONE, "status": "corrupt"}]


@pytest.mark.parametrize("bad", [ONE + "\n", None, 123])
def test_run_id_must_match_the_entire_string(tmp_path, bad):
    with pytest.raises(runs.RunNotFound):
        runs.RunStore(tmp_path).get(bad)


def test_competing_writers_publish_only_one_complete_record(tmp_path, monkeypatch):
    barrier = threading.Barrier(2)
    real_exists = Path.exists
    calls = threading.local()

    def together(path):
        result = real_exists(path)
        if path == tmp_path / f"{ONE}.json" and not getattr(calls, "seen", False):
            calls.seen = True
            barrier.wait(timeout=10)  # 두 저장이 첫 존재 검사를 함께 통과한 경쟁을 재현한다.
        return result

    monkeypatch.setattr(Path, "exists", together)

    def write(value):
        try:
            return runs.RunStore(tmp_path).save({"run_id": ONE, "value": value})
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [1, 2]))
    monkeypatch.setattr(Path, "exists", real_exists)
    [winner] = [r for r in results if r is not None]
    assert runs.RunStore(tmp_path).get(ONE) == winner
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob("*.lock"))


def test_failed_write_removes_temporary_file(tmp_path):
    with pytest.raises(TypeError):
        runs.RunStore(tmp_path).save({"run_id": ONE, "value": object()})
    assert not list(tmp_path.iterdir())


def test_failed_atomic_publication_does_not_leave_a_partial_record(tmp_path, monkeypatch):
    def unsupported(*args):
        raise OSError("publication failed")

    monkeypatch.setattr(runs.os, "replace", unsupported)
    with pytest.raises(OSError, match="publication failed"):
        runs.RunStore(tmp_path).save({"run_id": ONE, "value": 1})
    assert not list(tmp_path.iterdir())


def test_existing_lock_is_not_removed_or_ignored(tmp_path):
    lock = tmp_path / f"{ONE}.lock"
    lock.mkdir()
    with pytest.raises(FileExistsError):
        runs.RunStore(tmp_path).save({"run_id": ONE})
    assert lock.is_dir()
    assert not (tmp_path / f"{ONE}.json").exists()
