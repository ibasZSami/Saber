from unittest.mock import MagicMock, patch

from src.desktop.input_control import InputController


def _controller_with_mocked_backends():
    controller = InputController()
    controller._mouse = MagicMock()
    controller._keyboard = MagicMock()
    return controller


class TestClick:
    def test_click_sets_position_and_clicks(self):
        controller = _controller_with_mocked_backends()
        result = controller.click(100, 200)
        assert result is True
        assert controller._mouse.position == (100, 200)
        controller._mouse.click.assert_called_once()

    def test_click_right_button(self):
        from pynput.mouse import Button
        controller = _controller_with_mocked_backends()
        controller.click(1, 1, button="right")
        controller._mouse.click.assert_called_once_with(Button.right)

    def test_click_left_button_by_default(self):
        from pynput.mouse import Button
        controller = _controller_with_mocked_backends()
        controller.click(1, 1)
        controller._mouse.click.assert_called_once_with(Button.left)

    def test_click_exception_is_caught_and_returns_false(self):
        controller = _controller_with_mocked_backends()
        controller._mouse.click.side_effect = RuntimeError("boom")
        assert controller.click(1, 1) is False


class TestMove:
    def test_move_sets_position(self):
        controller = _controller_with_mocked_backends()
        result = controller.move(300, 400)
        assert result is True
        assert controller._mouse.position == (300, 400)

    def test_move_exception_is_caught(self):
        class _BoomMouse:
            @property
            def position(self):
                return (0, 0)

            @position.setter
            def position(self, value):
                raise RuntimeError("boom")

        controller = _controller_with_mocked_backends()
        controller._mouse = _BoomMouse()
        assert controller.move(1, 1) is False


class TestTypeText:
    def test_type_text_calls_keyboard_type(self):
        controller = _controller_with_mocked_backends()
        result = controller.type_text("olá mundo")
        assert result is True
        controller._keyboard.type.assert_called_once_with("olá mundo")

    def test_type_text_exception_is_caught(self):
        controller = _controller_with_mocked_backends()
        controller._keyboard.type.side_effect = RuntimeError("boom")
        assert controller.type_text("x") is False


class TestPressKey:
    def test_press_special_key_maps_to_pynput_key(self):
        from pynput.keyboard import Key
        controller = _controller_with_mocked_backends()
        result = controller.press_key("enter")
        assert result is True
        controller._keyboard.press.assert_called_once_with(Key.enter)
        controller._keyboard.release.assert_called_once_with(Key.enter)

    def test_press_key_is_case_insensitive(self):
        from pynput.keyboard import Key
        controller = _controller_with_mocked_backends()
        controller.press_key("ENTER")
        controller._keyboard.press.assert_called_once_with(Key.enter)

    def test_press_unmapped_key_passes_through_as_literal_character(self):
        controller = _controller_with_mocked_backends()
        controller.press_key("a")
        controller._keyboard.press.assert_called_once_with("a")

    def test_press_key_exception_is_caught(self):
        controller = _controller_with_mocked_backends()
        controller._keyboard.press.side_effect = RuntimeError("boom")
        assert controller.press_key("a") is False


class TestUnavailableBackend:
    def test_every_action_returns_false_when_pynput_is_unavailable(self):
        with patch("src.desktop.input_control.PYNPUT_AVAILABLE", False):
            controller = InputController()
            assert controller.available is False
            assert controller.click(1, 1) is False
            assert controller.move(1, 1) is False
            assert controller.type_text("x") is False
            assert controller.press_key("enter") is False
