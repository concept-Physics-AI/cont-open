"""Physics 열 비교 화면: 세 방법을 같은 정의의 편차로 한 표에. 판정하지 않고, 없는 값을 만들지 않는다."""
import math

import pytest

from cont.learn import available
from cont.view import physics_heat as ph
from cont.view.physics_page import render_physics


def test_finite_difference_rows_converge_second_order_and_reference_row_has_no_deviation():
    d = ph.compare_data()
    ref, *fd = [r for r in d["rows"] if r["method"] != "PINN"]
    assert ref["method"] == "해석식" and ref["rms"] is None and ref["status"] == "기준"
    assert [r["method"] for r in fd] == ["유한차분"] * 4
    rms = [r["rms"] for r in fd]
    assert rms == sorted(rms, reverse=True)
    assert all(1.8 < math.log2(a / b) < 2.2 for a, b in zip(rms, rms[1:])) and all(r["evidence"] == "E1" for r in fd)


@pytest.mark.skipif(not available(), reason="PyTorch가 없으면 PINN 행을 만들지 않는다")
def test_pinn_row_present_with_torch_and_is_labeled_e0():
    row = next(r for r in ph.compare_data()["rows"] if r["method"] == "PINN")
    assert row["evidence"] == "E0" and row["rms"] > 0 and "지문" in row["setting"]
    assert ph.compare_data()["final_dev"]["pinn"] and "PINN" in ph.render_heat_compare()


def test_without_torch_no_pinn_row_is_invented(monkeypatch):
    monkeypatch.setattr(ph, "available", lambda: False)
    ph.compare_data.cache_clear()
    try:
        d = ph.compare_data()
        assert not [r for r in d["rows"] if r["method"] == "PINN"] and d["pinn"] is None and "pinn" not in d["final_dev"]
        html = ph.render_heat_compare()
        assert "PINN 행을 만들지 않았습니다" in html and "없는 값을 채워 넣지 않았습니다" in html
    finally:
        ph.compare_data.cache_clear()


def test_page_shows_table_chart_and_no_judgment():
    page = render_physics()
    assert "열 작업대: 식, 수치해석, PINN 비교" in page and "<svg" in page and 'stroke-dasharray="6 3"' in page or not available()
    assert "판정하지 않습니다" in page and "합성 기준 문제" in page
    assert "허용" not in ph.render_heat_compare().replace("허용되는지는 판정하지 않습니다", "").replace("허용 오차를 정하지 않았습니다", "")
