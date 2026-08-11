import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QLabel, QSpinBox, QDoubleSpinBox
)
from src.config.settings import Settings

class SettingsWindow(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Configurações - Shimeji AI Companion")
        self.resize(500, 450)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: Geral
        general_tab = QWidget()
        g_layout = QFormLayout(general_tab)
        self.name_input = QLineEdit(self.settings.get("character_name", "Saber"))
        self.always_on_top_chk = QCheckBox("Manter Sempre no Topo")
        self.always_on_top_chk.setChecked(self.settings.get("always_on_top", True))
        self.click_through_chk = QCheckBox("Ativar Modo Click-Through (Não Bloquear Cliques)")
        self.click_through_chk.setChecked(self.settings.get("click_through", False))
        self.fps_input = QSpinBox()
        self.fps_input.setRange(1, 30)
        self.fps_input.setValue(self.settings.get("fps", 6))
        self.fps_input.setToolTip("Sprites têm poucos frames por animação; valores altos deixam o personagem tremido. Requer reiniciar o app.")
        g_layout.addRow("Nome da Personagem:", self.name_input)
        g_layout.addRow(self.always_on_top_chk)
        g_layout.addRow(self.click_through_chk)
        g_layout.addRow("Velocidade da Animação (FPS):", self.fps_input)
        tabs.addTab(general_tab, "Geral")

        # Tab 2: IA & Provedor
        ai_tab = QWidget()
        ai_layout = QFormLayout(ai_tab)
        self.ai_combo = QComboBox()
        self.ai_combo.addItems(["nvidia", "openai", "ollama"])
        self.ai_combo.setCurrentText(self.settings.get("ai_provider", "nvidia"))
        self.api_key_input = QLineEdit(self.settings.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("nvapi-... ou sk-...")
        self.ai_model_input = QLineEdit(self.settings.get("ai_model", "meta/llama-3.1-70b-instruct"))
        self.ai_model_input.setPlaceholderText("ex: meta/llama-3.1-70b-instruct ou gpt-4o-mini")
        ai_layout.addRow("Provedor de IA:", self.ai_combo)
        ai_layout.addRow("API Key:", self.api_key_input)
        ai_layout.addRow("Modelo:", self.ai_model_input)
        tabs.addTab(ai_tab, "IA")

        # Tab 3: Visão de Tela
        vision_tab = QWidget()
        v_layout = QFormLayout(vision_tab)
        self.vision_chk = QCheckBox("Ativar Visão de Tela (Screen Vision)")
        self.vision_chk.setChecked(self.settings.get("screen_monitoring_enabled", False))
        self.private_mode_chk = QCheckBox("Modo Privado (Nenhuma captura ou OCR)")
        self.private_mode_chk.setChecked(self.settings.get("private_mode", True))
        v_layout.addRow(self.vision_chk)
        v_layout.addRow(self.private_mode_chk)
        tabs.addTab(vision_tab, "Visão")

        layout.addWidget(tabs)

        save_btn = QPushButton("Salvar Configurações")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _save(self):
        self.settings.set("character_name", self.name_input.text().strip())
        self.settings.set("always_on_top", self.always_on_top_chk.isChecked())
        self.settings.set("click_through", self.click_through_chk.isChecked())
        self.settings.set("fps", self.fps_input.value())
        self.settings.set("ai_provider", self.ai_combo.currentText())
        self.settings.set("api_key", self.api_key_input.text().strip())
        self.settings.set("ai_model", self.ai_model_input.text().strip())
        self.settings.set("screen_monitoring_enabled", self.vision_chk.isChecked())
        self.settings.set("private_mode", self.private_mode_chk.isChecked())
        self.close()
