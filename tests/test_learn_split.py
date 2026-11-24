"""Y3: 묶음 단위 분할, 누출 검사, 분할 뒤 시간 창."""
from __future__ import annotations

import random

import pytest

from cont.learn.split import (CannotSplit, LeakageError, Split, assert_no_leakage, components, group_split, leakage,
                              make_windows)


def _rows(lots=8, per=5):
    return [{"lot": f"L{l}", "eq": f"E{l % 3}", "t": t} for l in range(lots) for t in range(per)]


def test_same_group_never_on_both_sides():
    rows = _rows()
    s = group_split(rows, ["lot"], seed=1)
    assert leakage(rows, s, ["lot"]) == {}
    assert set(s.train) | set(s.test) == set(range(len(rows))) and not set(s.train) & set(s.test)
    assert s.test_groups == 2 and s.groups == 8                      # 8묶음의 25%


def test_row_level_split_would_leak_and_check_fails():
    """행 단위로 섞은 가짜 분할을 검사기가 잡는다 (같은 묶음이 양쪽에 있으면 실패)."""
    rows = _rows()
    idx = list(range(len(rows))); random.Random(0).shuffle(idx)
    bad = Split(tuple(idx[10:]), tuple(idx[:10]), ("lot",), 8, 2, 0, "x")
    assert "lot" in leakage(rows, bad)
    with pytest.raises(LeakageError):
        assert_no_leakage(rows, bad)


def test_order_independent_and_deterministic():
    rows = _rows()
    a = group_split(rows, ["lot"], seed=3)
    shuffled = list(enumerate(rows)); random.Random(5).shuffle(shuffled)
    b = group_split([r for _, r in shuffled], ["lot"], seed=3)
    assert {rows[i]["lot"] for i in a.test} == {shuffled[i][1]["lot"] for i in b.test}
    assert group_split(rows, ["lot"], seed=3).fingerprint == a.fingerprint
    assert group_split(rows, ["lot"], seed=4).fingerprint != a.fingerprint


def test_shared_key_merges_groups_and_blocks_leakage_on_second_key():
    rows = _rows()                                                     # 설비 E0~E2가 로트를 서로 잇는다
    assert max(components(rows, ["lot", "eq"])) + 1 < 8
    rows2 = [{"lot": f"L{i}", "eq": f"E{i // 2}"} for i in range(8)]  # 로트 둘씩 같은 설비
    s = group_split(rows2, ["lot", "eq"], seed=0)
    assert leakage(rows2, s, ["lot", "eq"]) == {} and s.groups == 4


def test_everything_connected_cannot_split_and_says_why():
    rows = [{"lot": f"L{i}", "eq": "E0"} for i in range(6)]            # 한 설비가 모두를 잇는다
    with pytest.raises(CannotSplit, match="한 묶음"):
        group_split(rows, ["lot", "eq"])
    with pytest.raises(CannotSplit):
        group_split([{"lot": "A"}, {"lot": "A"}], ["lot"])


def test_missing_key_value_refuses():
    with pytest.raises(ValueError, match="값이 없습니다"):
        group_split([{"lot": "A"}, {"lot": None}, {"lot": "B"}], ["lot"])
    with pytest.raises(ValueError):
        group_split([{"lot": "A"}, {}, {"lot": "B"}], ["lot"])
    with pytest.raises(ValueError):
        group_split([{"lot": "A"}], [])


def test_windows_are_made_after_split_and_never_cross_groups():
    rows = _rows(lots=8, per=6)
    s = group_split(rows, ["lot"], seed=2)
    tr = make_windows(rows, s.train, ["lot"], "t", width=3, step=1)
    te = make_windows(rows, s.test, ["lot"], "t", width=3, step=3)
    assert tr and te
    for w in tr + te:
        assert len({rows[i]["lot"] for i in w}) == 1                   # 한 묶음 안
        assert [rows[i]["t"] for i in w] == sorted(rows[i]["t"] for i in w)
    assert not {i for w in tr for i in w} & {i for w in te for i in w}
    assert len(te) == s.test_groups * 2                                # 6행, 폭 3, 간격 3 → 묶음당 2창
    # 분할 전에 창을 만들어 나누면 같은 행을 나눠 갖는 창이 생긴다 (순서를 거꾸로 하면 안 되는 이유)
    all_w = make_windows(rows, range(len(rows)), ["lot"], "t", width=3, step=1)
    assert len(all_w) > len(tr) + len(te)


def test_config_values_are_used(monkeypatch):
    import cont.learn.split as sp
    monkeypatch.setattr(sp, "_config", lambda: {"test_fraction": 0.5, "seed": 9, "min_groups_per_side": 2})
    s = group_split(_rows(lots=8), ["lot"])
    assert s.test_groups == 4 and s.seed == 9
    with pytest.raises(CannotSplit):
        group_split(_rows(lots=3), ["lot"])                                     # 양쪽 2묶음씩 못 맞춘다
