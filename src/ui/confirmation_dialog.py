import logging
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox

from src.desktop.permission_policy import PolicyDecision


class ConfirmationBridge(QObject):
    """Lives on the GUI thread (created once in app.py). AgentCore's
    confirm_fn (see make_confirm_fn below) calls ask() from a background
    worker thread — handle_user_message and friends always run tool dispatch
    off the Qt main thread (see orchestrator.py).

    ask() emits _ask_requested, connected with Qt.BlockingQueuedConnection:
    Qt itself blocks the emitting (worker) thread until _show_dialog runs and
    returns on the receiving (GUI) thread. That's the standard Qt mechanism
    for a synchronous cross-thread call — no manual threading.Event needed,
    and no risk of touching QMessageBox off the GUI thread.

    The answer comes back via self._result, not a signal argument: PySide
    copies queued-connection arguments when crossing threads (confirmed — a
    mutable list passed as an argument does NOT retain identity across the
    boundary). An instance attribute has no such copy step, and Qt's
    blocking-connection wait provides the happens-before guarantee that makes
    reading it immediately after emit() safe.

    self._lock serializes concurrent ask() calls — two CONFIRM tools could in
    principle fire close together from different worker threads, and stacking
    two modal dialogs at once would be confusing as well as racy on
    self._result.

    Never call ask() from the GUI thread itself: BlockingQueuedConnection
    would deadlock waiting for a thread that's blocked waiting on itself.
    Every current caller (AgentCore.execute, always invoked from a worker
    thread) satisfies this."""

    _ask_requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._result = PolicyDecision.DECLINED
        self._ask_requested.connect(self._show_dialog, Qt.BlockingQueuedConnection)

    def ask(self, action: str, description: str) -> PolicyDecision:
        with self._lock:
            self._ask_requested.emit(action, description)
            return self._result

    def _show_dialog(self, action: str, description: str):
        box = QMessageBox()
        box.setWindowTitle("Silva pede permissão")
        # description can embed AI-controlled text (an app name, a URL) —
        # QMessageBox otherwise auto-detects rich text, so a stray '<'/'&' in
        # there (same class of bug fixed in chat_window.py) could visually
        # corrupt the exact message this dialog exists to show clearly.
        box.setTextFormat(Qt.PlainText)
        box.setText(description)

        once_btn = box.addButton("Permitir uma vez", QMessageBox.AcceptRole)
        session_btn = box.addButton("Permitir nesta sessão", QMessageBox.AcceptRole)
        always_btn = box.addButton("Permitir sempre", QMessageBox.AcceptRole)
        block_btn = box.addButton("Bloquear sempre", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("Cancelar", QMessageBox.RejectRole)
        # Default lands on Cancelar, not any of the persisting choices — an
        # accidental Enter press must never grant OR permanently block
        # something the user didn't deliberately choose.
        box.setDefaultButton(cancel_btn)

        box.exec()
        clicked = box.clickedButton()
        decision_by_button = {
            once_btn: PolicyDecision.ONCE,
            session_btn: PolicyDecision.SESSION,
            always_btn: PolicyDecision.ALWAYS,
            block_btn: PolicyDecision.BLOCKED,
            cancel_btn: PolicyDecision.DECLINED,
        }
        # Closing via the window's X / Escape reports clickedButton() as None
        # (no custom escape button set) — that must also land on DECLINED,
        # the only outcome that persists nothing, same fail-safe default.
        self._result = decision_by_button.get(clicked, PolicyDecision.DECLINED)


def make_confirm_fn(bridge: ConfirmationBridge):
    """Returns the confirm_fn AgentCore expects: (action, action_param,
    description) -> PolicyDecision. Wrapped in try/except so a dialog-layer
    bug denies (DECLINED, never persisted) instead of raising past AgentCore
    and leaving a CONFIRM tool's permission state undecided."""

    def confirm_fn(action: str, action_param, description: str) -> PolicyDecision:
        try:
            return bridge.ask(action, description)
        except Exception as e:
            logging.error(f"Confirmation dialog failed, denying '{action}' by default: {e}")
            return PolicyDecision.DECLINED

    return confirm_fn
