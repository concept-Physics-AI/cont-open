"""A05: 모델 계보."""
import pytest

from cont.learn.lineage import Lineage, LineageError, attach, dataset_sha256, file_sha256, from_dict, verify


def make(tmp_path, weights=b"w1", rows=({"a": 1},)):
    m = tmp_path / "m.bin"; m.write_bytes(weights)
    return m, Lineage(dataset_sha256(list(rows)), "split0123456789ab", "train0123456789", file_sha256(m), "eval-1", "abc1234")


def test_lineage_id_changes_with_weights_or_data(tmp_path):
    _, a = make(tmp_path); _, b = make(tmp_path, weights=b"w2"); _, c = make(tmp_path, rows=({"a": 2},))
    assert len({a.to_dict()["lineage_id"], b.to_dict()["lineage_id"], c.to_dict()["lineage_id"]}) == 3


def test_stale_model_or_data_is_refused(tmp_path):
    m, lin = make(tmp_path)
    d = lin.to_dict()
    assert verify(d, m, dataset_sha=lin.dataset_sha256, evaluation_version="eval-1").model_sha256 == lin.model_sha256
    m.write_bytes(b"retrained")                                        # 같은 이름, 다른 가중치
    with pytest.raises(LineageError, match="모델 파일"):
        verify(d, m)
    m.write_bytes(b"w1")
    with pytest.raises(LineageError, match="데이터"):
        verify(d, m, dataset_sha="0" * 64)
    with pytest.raises(LineageError, match="평가"):
        verify(d, m, evaluation_version="eval-2")
    with pytest.raises(LineageError, match="읽을 수 없"):
        verify(d, tmp_path / "gone.bin")


def test_empty_part_missing_part_and_tampered_id_are_refused(tmp_path):
    _, lin = make(tmp_path)
    with pytest.raises(LineageError, match="비어"):
        Lineage(lin.dataset_sha256, "", lin.training_fingerprint, lin.model_sha256, "e", "c")
    d = lin.to_dict(); d.pop("model_sha256")
    with pytest.raises(LineageError, match="빠진"):
        from_dict(d)
    d = lin.to_dict(); d["evaluation_version"] = "eval-9"
    with pytest.raises(LineageError, match="계보 ID"):
        from_dict(d)


def test_attach_does_not_mutate_or_overwrite(tmp_path):
    _, lin = make(tmp_path); _, other = make(tmp_path, weights=b"w2")
    rec = {"run_id": "run-000000000001"}
    out = attach(rec, lin)
    assert "lineage" not in rec and out["lineage"]["lineage_id"] == lin.to_dict()["lineage_id"]
    assert attach(out, lin) == out
    with pytest.raises(LineageError, match="이미 다른"):
        attach(out, other)


def test_dataset_hash_refuses_nan_and_depends_on_order():
    assert dataset_sha256([1, 2]) != dataset_sha256([2, 1])
    with pytest.raises(ValueError):
        dataset_sha256([float("nan")])
