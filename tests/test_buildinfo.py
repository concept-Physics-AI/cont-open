"""실행 중인 코드의 버전을 코드가 직접 적는다 (환경 변수 우선, 읽지 못하면 unknown)."""
import json
import threading
import urllib.request

from cont import buildinfo
from cont.service import runs
from cont.service.serve import make_server


def test_env_sha_wins_and_unreadable_is_unknown_not_guessed(monkeypatch):
    buildinfo.git_sha.cache_clear()
    monkeypatch.setenv("CONT_GIT_SHA", "abc1234def")
    assert buildinfo.git_sha() == "abc1234def"
    buildinfo.git_sha.cache_clear()
    monkeypatch.delenv("CONT_GIT_SHA")
    monkeypatch.setattr(buildinfo.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    assert buildinfo.git_sha() == "unknown"
    buildinfo.git_sha.cache_clear()


def test_banner_and_health_and_run_records_carry_the_build(monkeypatch):
    buildinfo.git_sha.cache_clear()
    monkeypatch.setenv("CONT_GIT_SHA", "feedface0001")
    b = buildinfo.build_info()
    assert b["git_sha"] == "feedface0001" and b["code_path"] and b["version"]
    assert "feedface0001" in buildinfo.banner()
    assert runs.model_version("fastening")["git_sha"] == "feedface0001"
    srv = make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        got = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/v1/health", timeout=10).read())
        assert got["ok"] is True and got["build"]["git_sha"] == "feedface0001"
    finally:
        srv.shutdown(); srv.server_close()
        buildinfo.git_sha.cache_clear()
