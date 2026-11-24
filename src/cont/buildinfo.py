"""실행 중인 코드가 어느 버전인가: 서버를 시작할 때와 실행 기록에 남긴다.

사람이 "최신 코드로 돌고 있다"고 말하는 것이 아니라 코드가 자기 위치와 커밋을 적는다.
커밋은 환경 변수 CONT_GIT_SHA가 있으면 그것을, 없으면 저장소의 git에서 읽는다. 읽지 못하면 "unknown"이라고 적고 짐작하지 않는다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import cont


@lru_cache(maxsize=1)
def git_sha() -> str:
    env = os.environ.get("CONT_GIT_SHA", "").strip()
    if env:
        return env
    root = Path(cont.__file__).resolve().parent
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) >= 7 else "unknown"


def build_info() -> dict[str, Any]:
    return {"version": cont.__version__, "git_sha": git_sha(), "code_path": str(Path(cont.__file__).resolve().parent),
            "python": sys.version.split()[0]}


def banner() -> str:
    b = build_info()
    return f"cont {b['version']} · commit {b['git_sha'][:12]} · {b['code_path']} · python {b['python']}"
