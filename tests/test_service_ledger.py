"""A26: 원본·파생물 지문과 부모 관계."""
import json

import pytest

from cont.service.ledger import Ledger, LedgerError


def test_source_page_and_derived_chain(tmp_path):
    lg = Ledger(tmp_path)
    src = lg.register("source", b"pdf-bytes", "P1", label="spec.pdf")
    page = lg.register("page", b"page-1", "P1", (src["id"],))
    out = lg.register("derived", b"table", "P1", (page["id"],))
    assert lg.ancestors(out["id"]) == [page["id"], src["id"]]
    assert lg.register("source", b"pdf-bytes", "P1", label="spec.pdf")["id"] == src["id"]      # 같은 항목은 그대로


def test_same_bytes_in_another_project_is_a_different_entry(tmp_path):
    lg = Ledger(tmp_path)
    assert lg.register("source", b"x", "P1")["id"] != lg.register("source", b"x", "P2")["id"]


def test_changed_or_replaced_file_is_not_accepted_as_evidence(tmp_path):
    lg = Ledger(tmp_path); src = lg.register("source", b"original", "P1")
    lg.check_content(src["id"], b"original")
    with pytest.raises(LedgerError, match="등록 때와 다릅니다"):
        lg.check_content(src["id"], b"replaced")


def test_cross_project_parent_and_bad_shapes_are_refused(tmp_path):
    lg = Ledger(tmp_path); a = lg.register("source", b"x", "P1")
    with pytest.raises(LedgerError, match="다른 프로젝트"):
        lg.register("derived", b"y", "P2", (a["id"],))
    with pytest.raises(LedgerError, match="부모가 없습니다"):
        lg.register("source", b"y", "P1", (a["id"],))
    with pytest.raises(LedgerError, match="부모가 하나 이상"):
        lg.register("derived", b"y", "P1")
    with pytest.raises(LedgerError, match="없는 항목"):
        lg.register("derived", b"y", "P1", ("art-0123456789abcdef",))
    with pytest.raises(LedgerError, match="올바르지"):
        lg.get("../etc/passwd")
    with pytest.raises(LedgerError, match="종류"):
        lg.register("weird", b"y", "P1")
    with pytest.raises(LedgerError, match="프로젝트 ID"):
        lg.register("source", b"y", "")


def test_tampered_record_is_refused_and_sources_are_checked_per_project(tmp_path):
    lg = Ledger(tmp_path); a = lg.register("source", b"x", "P1")
    assert lg.require_sources([a["id"]], "P1")[0]["id"] == a["id"]
    with pytest.raises(LedgerError, match="다른 프로젝트"):
        lg.require_sources([a["id"]], "P2")
    p = tmp_path / f"{a['id']}.json"; rec = json.loads(p.read_text(encoding="utf-8")); rec["sha256"] = "0" * 64
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(LedgerError, match="ID가 내용과"):
        lg.get(a["id"])


def test_execute_records_sources_and_refuses_foreign_or_missing_ones(tmp_path, monkeypatch):
    from cont.service import api, runs
    monkeypatch.setenv("CONT_RUN_DIR", str(tmp_path / "runs")); monkeypatch.setenv("CONT_LEDGER_DIR", str(tmp_path / "ledger"))
    lg = Ledger(tmp_path / "ledger")
    mine, other = lg.register("source", b"a", "P1"), lg.register("source", b"b", "P2")
    inputs = {"case": "sine_1d"}
    out = api.execute("heat", inputs, project_id="P1", sources=[mine["id"]])
    assert runs.store().get(out["run_id"])["sources"][0]["sha256"] == mine["sha256"]
    for bad, kw in ((other["id"], "다른 프로젝트"), ("art-0123456789abcdef", "없는 항목")):
        with pytest.raises(LedgerError, match=kw):
            api.execute("heat", inputs, project_id="P1", sources=[bad])
    with pytest.raises(ValueError, match="project_id"):
        api.execute("heat", inputs, sources=[mine["id"]])
    assert len(runs.store().list()) == 1                      # 거절된 요청은 기록을 남기지 않는다


def test_execute_without_ledger_refuses_sources(tmp_path, monkeypatch):
    from cont.service import api
    monkeypatch.setenv("CONT_RUN_DIR", str(tmp_path / "runs")); monkeypatch.delenv("CONT_LEDGER_DIR", raising=False)
    with pytest.raises(ValueError, match="장부"):
        api.execute("heat", {"case": "sine_1d"}, project_id="P1", sources=["art-0123456789abcdef"])
