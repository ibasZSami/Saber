import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QStackedWidget, QGroupBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal
from src.config.settings import Settings

DARK_STYLE = """
QWidget {
    background-color: #0f0f14;
    color: #e0e0e6;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #2a1f3d;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 15px;
    font-weight: bold;
    color: #d1b3ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QPushButton {
    background-color: #2a1f3d;
    border: 1px solid #4a2f6d;
    border-radius: 6px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3d2b59;
    border-color: #9e1b32;
}
QLineEdit, QComboBox {
    background-color: #161620;
    border: 1px solid #332647;
    border-radius: 4px;
    padding: 6px;
    color: #ffffff;
}
QCheckBox {
    spacing: 8px;
}
"""

class SetupWizard(QWidget):
    wizard_completed = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Shimeji AI Companion - Setup Wizard")
        self.resize(550, 420)
        self.setStyleSheet(DARK_STYLE)

        self.layout = QVBoxLayout(self)

        # Header
        self.title_lbl = QLabel("✨ Bem-vindo ao Shimeji AI Companion (Saber) ✨")
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #d1b3ff; margin-bottom: 10px;")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.title_lbl)

        # Stacked Pages
        self.stacked_widget = QStackedWidget()

        # Page 1: Character Name
        self.page1 = QGroupBox("Etapa 1: Nome da Personagem")
        p1_layout = QFormLayout(self.page1)
        self.name_input = QLineEdit(self.settings.get("character_name", "Saber"))
        p1_layout.addRow("Nome:", self.name_input)
        self.stacked_widget.addWidget(self.page1)

        # Page 2: AI Provider & API Key
        self.page2 = QGroupBox("Etapa 2: Inteligência Artificial")
        p2_layout = QFormLayout(self.page2)
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItems(["nvidia", "openai", "ollama"])
        self.api_key_input = QLineEdit(self.settings.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("nvapi-... ou sk-...")
        self.ai_model_input = QLineEdit(self.settings.get("ai_model", "meta/llama-3.1-70b-instruct"))
        self.ai_model_input.setPlaceholderText("ex: meta/llama-3.1-70b-instruct ou gpt-4o-mini")
        p2_layout.addRow("Provedor de IA:", self.ai_provider_combo)
        p2_layout.addRow("API Key:", self.api_key_input)
        p2_layout.addRow("Modelo:", self.ai_model_input)
        self.stacked_widget.addWidget(self.page2)

        # Page 3: Voice & Privacy
        self.page3 = QGroupBox("Etapa 3: Voz e Visão de Tela")
        p3_layout = QFormLayout(self.page3)
        self.screen_chk = QCheckBox("Ativar Visão da Tela (Screen Vision)")
        self.screen_chk.setChecked(self.settings.get("screen_monitoring_enabled", False))
        self.mic_chk = QCheckBox("Ativar Microfone por Padrão")
        self.mic_chk.setChecked(self.settings.get("microphone_enabled", False))
        p3_layout.addRow(self.screen_chk)
        p3_layout.addRow(self.mic_chk)
        self.stacked_widget.addWidget(self.page3)

        self.layout.addWidget(self.stacked_widget)

        # Buttons
        btn_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Anterior")
        self.next_btn = QPushButton("Próximo")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)

        btn_layout.addWidget(self.prev_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.next_btn)
        self.layout.addLayout(btn_layout)

        self._update_buttons()

    def _update_buttons(self):
        idx = self.stacked_widget.currentIndex()
        self.prev_btn.setEnabled(idx > 0)
        if idx == self.stacked_widget.count() - 1:
            self.next_btn.setText("Concluir e Iniciar")
        else:
            self.next_btn.setText("Próximo")

    def _prev_page(self):
        idx = self.stacked_widget.currentIndex()
        if idx > 0:
            self.stacked_widget.setCurrentIndex(idx - 1)
            self._update_buttons()

    def _next_page(self):
        idx = self.stacked_widget.currentIndex()
        if idx < self.stacked_widget.count() - 1:
            self.stacked_widget.setCurrentIndex(idx + 1)
            self._update_buttons()
        else:
            # Save settings
            self.settings.set("character_name", self.name_input.text().strip())
            self.settings.set("ai_provider", self.ai_provider_combo.currentText())
            self.settings.set("api_key", self.api_key_input.text().strip())
            self.settings.set("ai_model", self.ai_model_input.text().strip())
            self.settings.set("screen_monitoring_enabled", self.screen_chk.isChecked())
            self.settings.set("microphone_enabled", self.mic_chk.isChecked())
            self.wizard_completed.emit()
            self.close()
