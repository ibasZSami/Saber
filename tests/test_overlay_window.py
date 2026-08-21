from PySide6.QtCore import Qt

from src.ui.overlay_window import (
    MAX_FONT_PT, MIN_FONT_PT, OverlayBlock, OverlayWindow, _physical_to_logical, fit_font_size,
)


class TestWindowFlags:
    def test_is_frameless_always_on_top_and_click_through(self):
        window = OverlayWindow()
        flags = window.windowFlags()
        assert flags & Qt.FramelessWindowHint
        assert flags & Qt.WindowStaysOnTopHint
        assert flags & Qt.WindowTransparentForInput

    def test_has_translucent_background(self):
        window = OverlayWindow()
        assert window.testAttribute(Qt.WA_TranslucentBackground)

    def test_never_steals_focus(self):
        window = OverlayWindow()
        assert window.testAttribute(Qt.WA_ShowWithoutActivating)


class TestSetBlocksAndClear:
    def test_set_blocks_stores_them(self):
        window = OverlayWindow()
        blocks = [OverlayBlock(text="Olá", x=10, y=20, width=50, height=15)]
        window.set_blocks(blocks)
        assert window._blocks == blocks

    def test_clear_empties_blocks(self):
        window = OverlayWindow()
        window.set_blocks([OverlayBlock(text="x", x=0, y=0, width=1, height=1)])
        window.clear()
        assert window._blocks == []

    def test_starts_with_no_blocks(self):
        window = OverlayWindow()
        assert window._blocks == []


class TestPhysicalToLogical:
    def test_dpr_one_is_a_direct_mapping_plus_padding(self):
        block = OverlayBlock(text="x", x=100, y=200, width=50, height=20)
        rect = _physical_to_logical(block, dpr=1.0)
        assert rect.x() == 100 - 4
        assert rect.y() == 200 - 4
        assert rect.width() == 50 + 8
        assert rect.height() == 20 + 8

    def test_dpr_scales_coordinates_down(self):
        """A 150%-scaled display (dpr=1.5) must divide physical pixels down
        to logical ones, or the box lands in the wrong place relative to
        what Qt actually draws to."""
        block = OverlayBlock(text="x", x=150, y=300, width=75, height=30)
        rect = _physical_to_logical(block, dpr=1.5)
        assert rect.x() == 100 - 4
        assert rect.y() == 200 - 4
        assert rect.width() == 50 + 8
        assert rect.height() == 20 + 8


class TestFitFontSize:
    def test_short_text_in_a_big_box_uses_max_size(self):
        assert fit_font_size("Oi", box_width=1000, box_height=1000) == MAX_FONT_PT

    def test_long_text_in_a_small_box_shrinks_below_max(self):
        long_text = "Este é um texto bem mais longo do que a caixa original comportaria"
        size = fit_font_size(long_text, box_width=80, box_height=20)
        assert size < MAX_FONT_PT

    def test_never_shrinks_below_the_minimum(self):
        absurdly_long = "x" * 500
        size = fit_font_size(absurdly_long, box_width=10, box_height=5)
        assert size == MIN_FONT_PT

    def test_empty_text_uses_max_size(self):
        assert fit_font_size("", box_width=100, box_height=20) == MAX_FONT_PT
