from umd.app.catalog import CATALOG, accepts_kind
from umd.app.motion import TOKENS
from umd.app.tokens import BREAKPOINT_COMPACT, DARK, LIGHT, SIDEBAR_WIDTH, TOOLBAR_HEIGHT


def test_catalog_matches_prototype_counts():
    assert len(CATALOG) == 12
    assert sum(1 for item in CATALOG if item.selected) == 10
    assert sum(1 for item in CATALOG if item.kind == "video") == 2


def test_kind_filter():
    assert accepts_kind("image", "all")
    assert accepts_kind("video", "all")
    assert accepts_kind("image", "image")
    assert not accepts_kind("video", "image")
    assert accepts_kind("video", "video")


def test_motion_ranges_match_contract():
    assert 90 <= TOKENS["button_hover"].duration_ms <= 130
    assert 90 <= TOKENS["button_press"].duration_ms <= 120
    assert 150 <= TOKENS["sidebar_select"].duration_ms <= 210
    assert 260 <= TOKENS["inspector"].duration_ms <= 340
    assert TOKENS["inspector"].spring and TOKENS["inspector"].damping and TOKENS["inspector"].mass
    assert TOKENS["inspector"].cancel_policy == "retarget"
    assert TOKENS["inspector"].reduced_motion == "instant"
    assert 150 <= TOKENS["popover"].duration_ms <= 210
    assert 220 <= TOKENS["preview"].duration_ms <= 320
    assert 120 <= TOKENS["thumbnail_in"].duration_ms <= 180
    assert 140 <= TOKENS["grid_select"].duration_ms <= 210
    assert 160 <= TOKENS["success"].duration_ms <= 230


def test_color_tokens_present():
    for table in (LIGHT, DARK):
        assert table["accent"].startswith("#")
        assert table["text"] != table["window_bg"]
    assert SIDEBAR_WIDTH == 236
    assert TOOLBAR_HEIGHT == 60
    assert BREAKPOINT_COMPACT == 1100


def test_decompile_remains_blocked():
    from pathlib import Path

    text = Path("research/competitor_4k/LEGAL_LIMITS.md").read_text(encoding="utf-8")
    assert "WO-00E" in text
    assert "BLOCKED" in text
    assert "역컴파일" in text or "decompile" in text.lower() or "디스어셈블" in text
