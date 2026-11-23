"""ConT Fab 고르기: 목록에는 실제로 있는 엔진만, 미리보기는 엔진을 돌린 결과, 고른 것은 파일로."""
import json
import re

import pytest

from cont.fab.catalog import catalog, load, selection
from cont.fab.previews import PREVIEWS
from cont.fab.store import main, render_store
from cont.packs.fastening.pack import answer
from cont.dialogue.serve_fastening import example


def test_catalog_lists_only_engines_that_exist_and_every_item_has_a_real_preview():
    data = load()
    keys = [i["key"] for i in data["items"]]
    assert len(keys) == len(set(keys)) >= 9 and all(i["form"] in data["forms"] and i["preview"] in PREVIEWS for i in data["items"])
    items = catalog()
    assert [i["key"] for i in items] == keys
    for i in items:
        assert i["preview_html"].strip() and i["facts"] and i["form_label"] == data["forms"][i["form"]]
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert all(os.path.exists(os.path.join(root, i["doc"])) for i in data["items"] if i.get("doc"))      # 문서가 있는 것만 가리킨다


def test_preview_numbers_come_from_the_engines():
    j, l = example()
    a = answer(j, l)
    by = {i["key"]: i for i in catalog()}
    assert ["조립 체결력", f"{a.value('preload'):,.0f} N"] in by["fastening_diagram"]["facts"]
    assert any(f"{a.value('preload'):,.0f} N" in v for _, v in by["fastening_process"]["facts"])       # 마지막 칸 = 지금 설계의 체결력
    assert by["fastening_field"]["preview_html"].startswith("<svg") and by["signal_baseline"]["preview_html"].startswith("<svg")
    assert "관찰 사실" in by["guidance"]["preview_html"] and "원문과 대조하지 않은" in by["cutting_force"]["preview_note"]


def test_selection_is_the_seed_of_my_fab():
    s = selection(["fastening_field", "guidance", "fastening_field"], site="가상 라인")
    assert s["format"] == "cont-fab-selection" and s["site"] == "가상 라인" and [i["key"] for i in s["items"]] == ["fastening_field", "guidance"]
    assert all(i["name"] and i["needs"] for i in s["items"])
    with pytest.raises(ValueError):
        selection(["no_such_engine"])


def test_store_page_is_a_shop_without_prices_and_says_what_is_not_built(tmp_path):
    out = tmp_path / "fab.html"
    main(["--out", str(out)])
    page = out.read_text(encoding="utf-8")
    items = catalog()
    assert page.startswith("<!DOCTYPE html>") and page.count('<article class="item"') == len(items)
    assert all(x in page for x in ("ConT Fab", "물리 정보를 골라 내 Fab에 담으세요", 'id="q"', 'id="cart"', "바구니", "담기", "고른 것 내려받기", "my-fab.json"))
    assert "계산값 · 검증 전" in page and "실측과 대조하기 전" in page and "꾸리기 화면은 아직 만들지 않았습니다" in page
    assert not re.search(r"\d\s*(만\s*)?원|USD|\$\d|€", re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", page, flags=re.S))   # 가격이 없다
    data = json.loads(re.search(r'id="store-data">(.*?)</script>', page, re.S).group(1))
    assert [i["key"] for i in data["items"]] == [i["key"] for i in items]
    with pytest.raises(ValueError):
        render_store([], load()["forms"])
