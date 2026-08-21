import threading
import time
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.desktop.permission_policy import PolicyDecision
from src.ui.confirmation_dialog import ConfirmationBridge, make_confirm_fn

# Real thread + real Qt event loop (pumped via processEvents), only QMessageBox
# itself mocked out — this exercises the actual Qt.BlockingQueuedConnection
# cross-thread mechanism the FASE 1/2 confirmation flow depends on, not a
# stand-in.
_PUMP_TIMEOUT_S = 5.0


def _ask_on_worker_thread_and_pump(bridge, action, description):
    result = {}

    def _worker():
        result["value"] = bridge.ask(action, description)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    deadline = time.monotonic() + _PUMP_TIMEOUT_S
    while thread.is_alive():
        QApplication.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("ConfirmationBridge.ask() never returned — BlockingQueuedConnection wiring is broken")
    thread.join()
    return result["value"]


def _fake_message_box(clicked_button_name: str):
    """clicked_button_name selects which of the 5 addButton() calls (in the
    order _show_dialog makes them) clickedButton() should report — or None to
    simulate closing the dialog via X/Escape with no button clicked."""
    order = ["once", "session", "always", "block", "cancel"]
    box = MagicMock()
    buttons = {name: MagicMock(name=f"{name}_btn") for name in order}
    box.addButton.side_effect = [buttons[name] for name in order]
    box.clickedButton.return_value = buttons.get(clicked_button_name) if clicked_button_name else None
    return box, buttons


class TestConfirmationBridge:
    def test_once_button_returns_once(self):
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box("once")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            result = _ask_on_worker_thread_and_pump(bridge, "open_application", "desc")
        assert result == PolicyDecision.ONCE

    def test_session_button_returns_session(self):
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box("session")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            result = _ask_on_worker_thread_and_pump(bridge, "open_application", "desc")
        assert result == PolicyDecision.SESSION

    def test_always_button_returns_always(self):
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box("always")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            result = _ask_on_worker_thread_and_pump(bridge, "open_application", "desc")
        assert result == PolicyDecision.ALWAYS

    def test_block_button_returns_blocked(self):
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box("block")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            result = _ask_on_worker_thread_and_pump(bridge, "open_application", "desc")
        assert result == PolicyDecision.BLOCKED

    def test_cancel_button_returns_declined(self):
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box("cancel")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            result = _ask_on_worker_thread_and_pump(bridge, "open_application", "desc")
        assert result == PolicyDecision.DECLINED

    def test_closing_dialog_without_a_click_returns_declined(self):
        """X/Escape reports clickedButton() as None — must land on the same
        safe, non-persisted outcome as an explicit Cancel."""
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box(None)
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            result = _ask_on_worker_thread_and_pump(bridge, "open_application", "desc")
        assert result == PolicyDecision.DECLINED

    def test_forces_plain_text_so_ai_controlled_content_cant_break_rendering(self):
        """description can embed AI-controlled text (app name, URL) — a stray
        '<'/'&' must never be auto-detected as rich text and corrupt the exact
        message this dialog exists to show clearly (same bug class fixed in
        chat_window.py)."""
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box("once")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            _ask_on_worker_thread_and_pump(bridge, "open_url", "abre <b>isso</b> & mais")
        box.setTextFormat.assert_called_once_with(Qt.PlainText)

    def test_dialog_shows_the_given_description(self):
        bridge = ConfirmationBridge()
        box, _ = _fake_message_box("once")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            _ask_on_worker_thread_and_pump(bridge, "open_application", "Silva quer abrir o Google Chrome.")
        box.setText.assert_called_once_with("Silva quer abrir o Google Chrome.")

    def test_default_button_is_cancel_not_a_persisting_choice(self):
        """An accidental Enter press must never approve, permanently allow,
        or permanently block something the user didn't deliberately choose —
        see the class docstring's fail-safe rationale."""
        bridge = ConfirmationBridge()
        box, buttons = _fake_message_box("cancel")
        with patch("src.ui.confirmation_dialog.QMessageBox", return_value=box):
            _ask_on_worker_thread_and_pump(bridge, "open_application", "desc")
        box.setDefaultButton.assert_called_once_with(buttons["cancel"])


class TestMakeConfirmFn:
    def test_confirm_fn_delegates_to_bridge_ask(self):
        bridge = MagicMock()
        bridge.ask.return_value = PolicyDecision.ALWAYS

        confirm_fn = make_confirm_fn(bridge)
        result = confirm_fn("open_application", "chrome", "Silva quer abrir o Chrome.")

        assert result == PolicyDecision.ALWAYS
        bridge.ask.assert_called_once_with("open_application", "Silva quer abrir o Chrome.")

    def test_confirm_fn_declines_by_default_when_bridge_raises(self):
        bridge = MagicMock()
        bridge.ask.side_effect = RuntimeError("boom")

        confirm_fn = make_confirm_fn(bridge)
        result = confirm_fn("open_application", "chrome", "desc")

        assert result == PolicyDecision.DECLINED
