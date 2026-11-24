"""컨트롤타워 최소판: 규칙을 사람 기억이 아니라 테스트로 지킨다.

점검 세 가지: (1) 비밀값과 PC 경로가 올라가지 않았는가, (2) "검증 완료" 같은 주장이 없는가, (3) 상태 파일이 실제 파일과 맞는가.
공급자 SDK 직접 호출과 중복 정의는 tests/test_authority.py가 맡는다.
이 점검이 보지 못하는 것: 물리 값이 엔진에서만 나오는지, 계산이 물리적으로 맞는지.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "dist"}
TEXT = {".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".json", ".html", ".example", ".cmd"}
SELF = Path(__file__).resolve()


def _files(roots=None):
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or SKIP & set(p.relative_to(ROOT).parts) or p.resolve() == SELF:
            continue
        if any(s.endswith(".egg-info") for s in p.relative_to(ROOT).parts):
            continue
        if p.suffix in TEXT or p.name in {".env.example", ".gitignore"}:
            if roots is None or p.relative_to(ROOT).parts[0] in roots or p.name in roots:
                yield p


SECRETS = [r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"AKIA[0-9A-Z]{16}",
           r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"]
PC_PATHS = [r"Z:\\", r"C:\\Users", r"C:\\Dev", r"OneDrive", r"/Users/", r"/home/[a-z]"]
CLAIMS = re.compile(r"검증 ?완료|검증됨|검증이 끝")
NEGATION = ("전", "않", "없", "아직", "구분", "아니", "못")


def test_no_secrets_in_repository():
    bad = [f"{p.relative_to(ROOT)}: {pat}" for p in _files() for pat in SECRETS if re.search(pat, p.read_text(encoding="utf-8", errors="ignore"))]
    assert not bad, f"비밀값처럼 보이는 것이 있습니다: {bad}"


def test_no_personal_pc_paths_in_public_repository():
    bad = [f"{p.relative_to(ROOT)}: {pat}" for p in _files() for pat in PC_PATHS if re.search(pat, p.read_text(encoding="utf-8", errors="ignore"))]
    assert not bad, f"공개 저장소에 PC 경로가 있습니다 (CLAUDE.md 규칙 8): {bad}"


def test_no_validated_claim_without_a_qualifier():
    bad = []
    for p in _files({"src", "config", "docs", "README.md", "ARCHITECTURE.md"}):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").split("\n"), 1):
            if CLAIMS.search(line) and not any(n in line for n in NEGATION):
                bad.append(f"{p.relative_to(ROOT)}:{i}")
    assert not bad, f"검증됐다는 주장이 있습니다. 엔진이 돌았다는 것은 물리적으로 검증됐다는 뜻이 아닙니다: {bad}"


def test_checkers_catch_what_they_should():
    assert re.search(SECRETS[0], "key = sk-" + "a" * 24) and re.search(SECRETS[1], "ghp_" + "b" * 24)
    assert re.search(PC_PATHS[0], "Z:\\data") and re.search(PC_PATHS[3], "C:/x/OneDrive/y")
    assert CLAIMS.search("이 결과는 검증 완료되었다") and CLAIMS.search("검증됨")


STATES = {"있음", "뼈대", "없음"}


def test_status_file_matches_real_files():
    d = yaml.safe_load((ROOT / "config" / "status.yaml").read_text(encoding="utf-8"))
    keys = [i["key"] for i in d["items"]]
    assert len(keys) == len(set(keys))
    for i in d["items"]:
        assert set(i) == {"key", "name", "status", "scope", "evidence"}, f"{i['key']}: 항목 이름이 틀렸습니다 (쉼표가 든 글은 따옴표로 묶어야 합니다): {sorted(i)}"
        assert i["status"] in STATES and i["scope"], i["key"]
        if i["status"] == "없음":
            assert not i["evidence"], f"{i['key']}: 없다고 적었는데 증거 파일이 있습니다"
        else:
            assert i["evidence"], f"{i['key']}: {i['status']}인데 증거 파일이 없습니다"
            for e in i["evidence"]:
                assert (ROOT / e).exists(), f"{i['key']}: {e}가 없습니다"


def test_status_file_lists_all_products_and_modules():
    d = yaml.safe_load((ROOT / "config" / "status.yaml").read_text(encoding="utf-8"))
    keys = {i["key"] for i in d["items"]}
    assert {"product_studio", "product_physics", "product_fab"} <= keys
    assert {f"c{n}_" for n in range(1, 8)} <= {k[:3] for k in keys}


def test_pr_template_asks_about_authority_and_claims():
    t = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    for need in ("권위 영향", "아키텍처", "pytest", "검증"):
        assert need in t
