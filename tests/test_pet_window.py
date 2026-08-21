from unittest.mock import MagicMock, patch

from PySide6.QtCore import QRect

from src.ui.pet_window import PetWindow, BASE_WINDOW_SIZE, MIN_WINDOW_SIZE


def _fake_animation_manager():
    mgr = MagicMock()
    mgr.get_current_frame.return_value = None  # avoid needing a real QPixmap
    return mgr


def _make_window(screen_width, screen_height, **kwargs):
    fake_screen = MagicMock()
    fake_screen.availableGeometry.return_value = QRect(0, 0, screen_width, screen_height)
    with patch("src.ui.pet_window.QApplication.primaryScreen", return_value=fake_screen):
        return PetWindow(_fake_animation_manager(), MagicMock(), **kwargs)


class TestAdaptiveWindowSize:
    def test_uses_base_size_on_a_large_screen(self):
        """A big/high-res monitor has plenty of room — no need to shrink below
        the usual 300px pet size."""
        window = _make_window(1920, 1080)
        assert window.width() == BASE_WINDOW_SIZE
        assert window.height() == BASE_WINDOW_SIZE

    def test_shrinks_on_a_small_scaled_screen(self):
        """Regression test: on a small/DPI-scaled display (e.g. 1067x643
        logical, a real laptop at 150% scaling), a fixed 300px window ate up
        nearly half the screen height and visually read as parked in the
        middle instead of docked in a corner."""
        window = _make_window(1067, 643)
        assert window.width() < BASE_WINDOW_SIZE
        assert window.width() == int(643 * 0.3)

    def test_never_shrinks_below_the_minimum(self):
        window = _make_window(300, 300)
        assert window.width() >= MIN_WINDOW_SIZE

    def test_scale_setting_multiplies_the_computed_size(self):
        base = _make_window(1920, 1080, scale=1.0)
        scaled = _make_window(1920, 1080, scale=0.5)
        assert scaled.width() == int(base.width() * 0.5)

    def test_minimum_still_holds_when_scale_would_push_below_it(self):
        """Regression test: MIN_WINDOW_SIZE used to be clamped BEFORE
        multiplying by scale, so a scale < 1.0 on a screen where the
        pre-scale size was already at the floor pushed the final size back
        below it — scale=0 produced a fully invisible 0px window."""
        window = _make_window(1067, 643, scale=0.3)
        assert window.width() >= MIN_WINDOW_SIZE

    def test_scale_zero_does_not_produce_an_invisible_window(self):
        window = _make_window(1067, 643, scale=0.0)
        assert window.width() >= MIN_WINDOW_SIZE


class TestCornerAnchoring:
    def test_docks_to_bottom_right_with_margin(self):
        window = _make_window(1067, 643, window_margin_x=40, window_margin_y=40)
        assert window.x() == 1067 - window.width() - 40
        assert window.y() == 643 - window.height() - 40

    def test_window_bottom_and_right_edges_stay_in_the_lower_right_quadrant(self):
        """The actual regression the user reported: the window's top edge
        used to land at/above the screen's vertical midpoint on a small
        screen, so it looked centered rather than corner-docked."""
        window = _make_window(1067, 643)
        assert window.y() > 643 / 2
        assert window.x() > 1067 / 2
