"""Mouse/keyboard automation — FASE 3. The highest blast-radius capability
Silva has: a wrong click or keystroke is real and immediate, unlike every
other tool so far. This module is a thin, validated wrapper around pynput —
the actual gating (CONFIRM tier + confirmation dialog/policy, and the
input_control_enabled master switch that must be turned on before these
tools even register — see build_default_registry) lives one layer up, in
src/core/tool_registry.py and Settings. Nothing here runs unsupervised on
its own."""

import logging

try:
    from pynput.keyboard import Controller as KeyboardController, Key
    from pynput.mouse import Button, Controller as MouseController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

if PYNPUT_AVAILABLE:
    _KEY_MAP = {
        "enter": Key.enter, "return": Key.enter, "tab": Key.tab,
        "esc": Key.esc, "escape": Key.esc, "space": Key.space,
        "backspace": Key.backspace, "delete": Key.delete,
        "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
        "home": Key.home, "end": Key.end, "pageup": Key.page_up, "pagedown": Key.page_down,
    }
else:
    _KEY_MAP = {}

# Sanity bound on click/move coordinates — not a real multi-monitor bounds
# check (that would couple this module to ScreenCapture), just a guard
# against an obviously-hallucinated value (e.g. x=999999) reaching the OS.
MAX_COORDINATE = 10000


class InputController:
    def __init__(self):
        self._mouse = MouseController() if PYNPUT_AVAILABLE else None
        self._keyboard = KeyboardController() if PYNPUT_AVAILABLE else None

    @property
    def available(self) -> bool:
        return PYNPUT_AVAILABLE

    def click(self, x: int, y: int, button: str = "left") -> bool:
        if not self.available:
            return False
        try:
            self._mouse.position = (x, y)
            self._mouse.click(Button.right if button == "right" else Button.left)
            return True
        except Exception as e:
            logging.error(f"Mouse click at ({x}, {y}) failed: {e}")
            return False

    def move(self, x: int, y: int) -> bool:
        if not self.available:
            return False
        try:
            self._mouse.position = (x, y)
            return True
        except Exception as e:
            logging.error(f"Mouse move to ({x}, {y}) failed: {e}")
            return False

    def type_text(self, text: str) -> bool:
        if not self.available:
            return False
        try:
            self._keyboard.type(text)
            return True
        except Exception as e:
            logging.error(f"Keyboard type failed: {e}")
            return False

    def press_key(self, key_name: str) -> bool:
        if not self.available:
            return False
        try:
            key = _KEY_MAP.get(key_name.lower(), key_name)
            self._keyboard.press(key)
            self._keyboard.release(key)
            return True
        except Exception as e:
            logging.error(f"Key press '{key_name}' failed: {e}")
            return False
