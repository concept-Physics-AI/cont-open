"""문서 상태 표시 점검: 모든 문서에 상태가 있고, docs/INDEX.md와 같다."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = {"정본", "보조", "참고", "기록", "보류"}
PAT = re.compile(r"^> 상태: (\S+)\s*$", re.M)


def _docs():
    files = [ROOT / "ARCHITECTURE.md", ROOT / "CLAUDE.md", ROOT / "README.md"]
    return files + sorted((ROOT / "docs").glob("*.md"))


def _status(path):
    head = "\n".join(path.read_text(encoding="utf-8").split("\n")[:6])
    m = PAT.search(head)
    return m.group(1) if m else None


def test_every_doc_has_known_status_near_title():
    for p in _docs():
        s = _status(p)
        assert s in STATUS, f"{p.relative_to(ROOT)}: 제목 아래에 '> 상태: ...' 한 줄이 필요합니다 (허용: {sorted(STATUS)})"


def test_index_lists_every_doc_with_same_status():
    index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    listed = {}
    for m in re.finditer(r"^\| \[([^\]]+)\]\([^)]*\) \| (\S+) \|$", index, re.M):
        listed[m.group(1)] = m.group(2)
    for p in _docs():
        rel = p.relative_to(ROOT).as_posix()
        if rel == "docs/INDEX.md":
            continue
        assert rel in listed, f"docs/INDEX.md에 {rel}이(가) 없습니다"
        assert listed[rel] == _status(p), f"{rel}: 목록의 상태와 문서 머리말이 다릅니다"
    extra = set(listed) - {p.relative_to(ROOT).as_posix() for p in _docs()}
    assert not extra, f"목록에만 있는 문서: {sorted(extra)}"


def test_architecture_declares_the_status_words():
    arch = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for w in STATUS:
        assert w in arch
