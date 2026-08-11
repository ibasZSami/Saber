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

    def __init__(self, character_name: str = "Saber"):
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

        self.append_message(self.character_name, f"Oi! Estou acompanhando você. Como posso ajudar?")

    def append_message(self, sender: str, text: str):
        color = "#d1b3ff" if sender == self.character_name else "#64b5f6"
        formatted = f"<b style='color: {color};'>{sender}:</b> {text}<br>"
        self.chat_display.append(formatted)

    def _send(self):
        text = self.input_field.text().strip()
        if text:
            self.append_message("Você", text)
            self.input_field.clear()
            self.message_sent.emit(text)
