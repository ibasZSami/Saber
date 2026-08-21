import html
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

CHAT_STYLE = """
QWidget {
    background-color: #0f0f14;
    color: #e0e0e6;
    font-family: 'Segoe UI', sans-serif;
}
QTextEdit {
    background-color: #161620;
    border: 1px solid #2a1f3d;
    border-radius: 8px;
    padding: 10px;
    font-size: 13px;
}
QLineEdit {
    background-color: #161620;
    border: 1px solid #332647;
    border-radius: 6px;
    padding: 8px;
    color: #ffffff;
    font-size: 13px;
}
QPushButton {
    background-color: #2a1f3d;
    border: 1px solid #9e1b32;
    border-radius: 6px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3d2b59;
}
"""

class ChatWindow(QWidget):
    message_sent = Signal(str)
    # Internal-only: append_message() is called by EventBus subscribers and
    # orchestrator callbacks that may run on a background thread (spontaneous
    # speech, background-task announcements, voice transcription) — EventBus
    # is a plain Python callback list with no Qt thread marshaling, so calling
    # a QTextEdit method directly from those threads is a cross-thread Qt call
    # (undefined behavior, can crash or corrupt the widget). Routing through
    # this signal with an explicit QueuedConnection makes append_message safe
    # to call from any thread: the emit() just queues an event, and Qt runs
    # _append_message on this widget's own (GUI) thread.
    _append_message_requested = Signal(str, str)

    def __init__(self, character_name: str = "Silva"):
        super().__init__()
        self.character_name = character_name
        self.setWindowTitle(f"Conversar com {self.character_name}")
        self.resize(450, 550)
        self.setStyleSheet(CHAT_STYLE)

        layout = QVBoxLayout(self)

        # Header
        self.header_lbl = QLabel(f"🔮 {self.character_name} - Desktop Companion")
        self.header_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #d1b3ff; margin-bottom: 5px;")
        layout.addWidget(self.header_lbl)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)

        # Input Area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Digite uma mensagem ou pergunte sobre a tela...")
        self.input_field.returnPressed.connect(self._send)

        self.send_btn = QPushButton("Enviar")
        self.send_btn.clicked.connect(self._send)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        # AutoConnection, not a hardcoded QueuedConnection: same-thread callers
        # (the overwhelming majority — GUI-thread code calling append_message
        # directly) run synchronously, matching EventBus's own design
        # principle (src/core/event_bus.py) instead of paying an extra
        # event-loop round trip on every call. Cross-thread callers (worker
        # threads via EventBus) still get queued automatically — that part is
        # unaffected, Qt decides per-emit based on the calling thread.
        self._append_message_requested.connect(self._append_message, Qt.AutoConnection)

        self.append_message(self.character_name, f"Oi! Estou acompanhando você. Como posso ajudar?")

    def append_message(self, sender: str, text: str):
        self._append_message_requested.emit(sender, text)

    def _append_message(self, sender: str, text: str):
        color = "#d1b3ff" if sender == self.character_name else "#64b5f6"
        formatted = f"<b style='color: {color};'>{html.escape(sender)}:</b> {html.escape(text)}<br>"
        self.chat_display.append(formatted)

    def _send(self):
        text = self.input_field.text().strip()
        if text:
            self.append_message("Você", text)
            self.input_field.clear()
            self.message_sent.emit(text)
