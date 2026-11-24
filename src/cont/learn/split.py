"""평가 분할 도구 (Y3): 묶음(그룹) 단위 분할, 분할 뒤 시간 창 만들기, 누출 검사. torch가 필요 없다.

행 단위로 섞어 나누면 같은 로트·설비의 이웃 행이 훈련과 시험에 갈려 들어가 점수가 부풀려진다.
그래서 키(로트, 설비 등)를 정해 같은 키를 공유하는 행은 항상 같은 쪽에 둔다.
키가 여럿이면 하나라도 공유하는 행끼리 한 묶음으로 잇는다. 모든 행이 한 묶음으로 이어지면 나눌 수 없다고 알린다.
숫자 기준(비율, 시드)은 config/learn/split.yaml에 있다. 이 도구는 합격 여부를 판정하지 않는다. 누출이 있는지만 알린다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

_CFG = Path(__file__).resolve().parents[3] / "config" / "learn" / "split.yaml"


class CannotSplit(ValueError):
    """묶음이 모자라 훈련과 시험으로 나눌 수 없다 (이유를 메시지에 담는다)."""


class LeakageError(AssertionError):
    """같은 묶음이 훈련과 시험 양쪽에 있다."""


def _config() -> dict[str, Any]:
    return yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}


@dataclass(frozen=True)
class Split:
    train: tuple[int, ...]          # 행 번호
    test: tuple[int, ...]
    keys: tuple[str, ...]
    groups: int                     # 묶음 수
    test_groups: int
    seed: int
    fingerprint: str                # 입력 키 값과 분할 결과의 지문 (같은 자료로 나눴는지 확인)


def components(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[int]:
    """행마다 묶음 번호. 키 값 하나라도 같으면 같은 묶음 (연결 요소). 번호는 첫 등장 순서."""
    if not keys:
        raise ValueError("묶음 키가 없습니다")
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for key in keys:
        first: dict[Any, int] = {}
        for i, row in enumerate(rows):
            if key not in row or row[key] is None or row[key] != row[key]:     # 없음, None, NaN
                raise ValueError(f"{i}번 행에 '{key}' 값이 없습니다. 묶음을 정할 수 없어 분할하지 않습니다")
            v = row[key]
            if v in first:
                parent[find(i)] = find(first[v])
            else:
                first[v] = i
    label: dict[int, int] = {}
    out = []
    for i in range(len(rows)):
        out.append(label.setdefault(find(i), len(label)))
    return out


def _rank(group_id: int, seed: int, members: str) -> str:
    return hashlib.sha256(f"{seed}|{members}".encode()).hexdigest()


def group_split(rows: Sequence[Mapping[str, Any]], keys: Sequence[str], test_fraction: float | None = None,
                seed: int | None = None, min_groups_per_side: int | None = None) -> Split:
    """묶음 단위로 훈련/시험을 나눈다. 행 순서와 무관하고 같은 입력, 같은 시드면 같은 결과다."""
    cfg = _config()
    frac = cfg["test_fraction"] if test_fraction is None else test_fraction
    seed = int(cfg["seed"] if seed is None else seed)
    need = int(cfg["min_groups_per_side"] if min_groups_per_side is None else min_groups_per_side)
    if not 0.0 < frac < 1.0:
        raise ValueError("test_fraction은 0과 1 사이여야 합니다")
    comp = components(rows, keys)
    n_groups = (max(comp) + 1) if comp else 0
    if n_groups < 2 * need:
        raise CannotSplit(f"묶음이 {n_groups}개뿐입니다. 훈련과 시험에 각각 {need}개 이상 필요합니다."
                          + (" 키를 하나라도 공유하는 행을 한 묶음으로 이어서, 모든 행이 한 묶음이 되었습니다." if n_groups == 1 and len(rows) > 1 else ""))
    # 묶음의 정체는 번호가 아니라 안에 든 키 값들로 정한다 (행 순서가 바뀌어도 같은 분할)
    ident: dict[int, str] = {}
    for g in range(n_groups):
        vals = sorted({repr(rows[i][k]) for i, c in enumerate(comp) if c == g for k in keys})
        ident[g] = "|".join(vals)
    order = sorted(range(n_groups), key=lambda g: _rank(g, seed, ident[g]))
    n_test = min(max(round(frac * n_groups), need), n_groups - need)
    test_set = set(order[:n_test])
    train = tuple(i for i, c in enumerate(comp) if c not in test_set)
    test = tuple(i for i, c in enumerate(comp) if c in test_set)
    fp = hashlib.sha256(json.dumps({"keys": list(keys), "vals": [[repr(r[k]) for k in keys] for r in rows],
                                    "test": list(test), "seed": seed}, ensure_ascii=False).encode()).hexdigest()[:16]
    return Split(train, test, tuple(keys), n_groups, n_test, seed, fp)


def leakage(rows: Sequence[Mapping[str, Any]], split: Split, keys: Sequence[str] | None = None) -> dict[str, list[Any]]:
    """키마다 훈련과 시험에 모두 나타나는 값. 비어 있으면 누출 없음. 분할에 쓰지 않은 키도 검사할 수 있다 (예: 설비)."""
    out: dict[str, list[Any]] = {}
    for k in (keys or split.keys):
        tr = {rows[i][k] for i in split.train}
        te = {rows[i][k] for i in split.test}
        shared = sorted(tr & te, key=repr)
        if shared:
            out[k] = shared
    return out


def assert_no_leakage(rows: Sequence[Mapping[str, Any]], split: Split, keys: Sequence[str] | None = None) -> None:
    found = leakage(rows, split, keys)
    if found:
        raise LeakageError("훈련과 시험에 같은 값이 있습니다: " + "; ".join(f"{k}={v}" for k, v in found.items()))
    if set(split.train) & set(split.test):
        raise LeakageError("같은 행이 훈련과 시험에 모두 있습니다")


def make_windows(rows: Sequence[Mapping[str, Any]], indices: Sequence[int], group_keys: Sequence[str], time_key: str,
                 width: int, step: int) -> list[tuple[int, ...]]:
    """분할이 끝난 한쪽(indices)에서만 시간 창을 만든다. 창은 한 묶음 안에서, 시간순 연속 행으로만 이룬다.
    창이 묶음 경계를 넘지 않으므로 훈련 창과 시험 창이 같은 행을 나눠 갖지 않는다."""
    if width < 1 or step < 1:
        raise ValueError("width와 step은 1 이상이어야 합니다")
    comp = components([rows[i] for i in indices], group_keys)
    by_group: dict[int, list[int]] = {}
    for pos, c in enumerate(comp):
        by_group.setdefault(c, []).append(indices[pos])
    out: list[tuple[int, ...]] = []
    for members in by_group.values():
        members.sort(key=lambda i: rows[i][time_key])
        for s in range(0, len(members) - width + 1, step):
            out.append(tuple(members[s:s + width]))
    return out
