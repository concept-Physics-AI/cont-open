"""상단 Studio · Physics · FAB 전환 틀과 Physics 화면."""
import pytest

from cont.view.physics_page import engines_ready, engines_wanted, render_physics
from cont.view.switcher import product_urls, switcher_html, with_switcher


def test_switcher_marks_current_and_links_others(monkeypatch):
    monkeypatch.setenv("CONT_FAB_URL", "http://example.test/fab")
    h = switcher_html("physics")
    assert h.count('aria-current="page"') == 1 and ">Physics</a>" in h and "http://example.test/fab" in h
    assert [h.index(n) for n in ("Studio", "Physics", "FAB")] == sorted(h.index(n) for n in ("Studio", "Physics", "FAB"))


def test_unknown_address_is_not_a_link(monkeypatch):
    monkeypatch.setenv("CONT_STUDIO_URL", "")
    monkeypatch.setattr("cont.view.switcher.product_urls", lambda: {"studio": "", "physics": "x", "fab": "y"})
    h = switcher_html("fab")
    assert 'class="tab"' in h and "Studio" in h


def test_unknown_product_and_bad_page():
    with pytest.raises(KeyError):
        switcher_html("nope")
    with pytest.raises(ValueError):
        with_switcher("<p>no style</p>", "fab")
    assert set(product_urls()) == {"studio", "physics", "fab"}


def test_all_screens_carry_the_switcher(tmp_path):
    from cont.fab.catalog import catalog
    from cont.fab.store import render_store
    from cont.view import diagnosis_app
    from cont.dialogue.serve_diagnosis import main as diag_main
    assert 'aria-current="page" href' in render_store(catalog()) and 'class="psw"' in render_physics()
    out = tmp_path / "d.html"
    diag_main(["--out", str(out)])
    assert 'class="psw"' in out.read_text(encoding="utf-8")
    from cont.dialogue.serve_fastening import main as fast_main
    out2 = tmp_path / "f.html"
    fast_main(["--out", str(out2)])
    page = out2.read_text(encoding="utf-8")
    assert 'class="psw"' in page and ">Studio</a>" in page


def test_physics_page_lists_real_engines_and_waiting_ones():
    from cont.packs import names
    ready = engines_ready()
    assert {x["key"] for x in ready if x["pack"]} == set(names())
    wanted = engines_wanted()
    assert wanted and wanted == sorted(wanted, key=lambda x: (-len(x["types"]), x["name"]))
    page = render_physics()
    assert "지금 있는 엔진" in page and "아직 없는 엔진" in page and "계산값" in page
