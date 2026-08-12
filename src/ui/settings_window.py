import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QPushButton, QLabel, QSpinBox, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
)
from src.config.settings import Settings
from src.core import autostart

# (display label, edge_tts voice name)
VOICE_OPTIONS = [
    ("Masculina (Antonio)", "pt-BR-AntonioNeural"),
    ("Feminina (Francisca)", "pt-BR-FranciscaNeural"),
]


def _pitch_str_to_hz(pitch_str: str) -> int:
    try:
        return int(str(pitch_str).replace("Hz", "").strip())
    except (ValueError, TypeError):
        return 0

class SettingsWindow(QWidget):
    def __init__(self, settings: Settings, permission_manager=None):
        super().__init__()
        self.settings = settings
        # Lets a saved allowlist change take effect immediately — without this,
        # DesktopActionManager keeps using the snapshot PermissionManager took
        # at orchestrator startup until the app is restarted.
        self.permission_manager = permission_manager
        self.setWindowTitle("Configurações - Silva")
        self.resize(500, 450)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: Geral
        general_tab = QWidget()
        g_layout = QFormLayout(general_tab)
        self.name_input = QLineEdit(self.settings.get("character_name", "Silva"))
        self.always_on_top_chk = QCheckBox("Manter Sempre no Topo")
        self.always_on_top_chk.setChecked(self.settings.get("always_on_top", True))
        self.click_through_chk = QCheckBox("Ativar Modo Click-Through (Não Bloquear Cliques)")
        self.click_through_chk.setChecked(self.settings.get("click_through", False))
        self.spontaneous_talk_chk = QCheckBox("Fala Espontânea (comentários por conta própria, como numa chamada)")
        self.spontaneous_talk_chk.setChecked(self.settings.get("spontaneous_talk_enabled", True))
        self.spontaneous_talk_chk.setToolTip(
            "Também pode ligar/desligar por voz ou texto: \"pare de falar aleatoriamente\" / \"ativar falar aleatoriamente\"."
        )
        self.autostart_chk = QCheckBox("Iniciar Automaticamente com o Windows")
        self.autostart_chk.setChecked(autostart.is_enabled())
        self.autostart_chk.setToolTip("Pode ligar/desligar a qualquer momento aqui, sem precisar reinstalar nada.")
        self.nerd_mode_chk = QCheckBox("Modo Nerd (mais proativo)")
        self.nerd_mode_chk.setChecked(self.settings.get("nerd_mode_enabled", False))
        self.nerd_mode_chk.setToolTip(
            "Também pode ligar/desligar por voz ou texto: \"vira nerd\" / \"desliga o modo nerd\"."
        )
        g_layout.addRow("Nome da Personagem:", self.name_input)
        g_layout.addRow(self.always_on_top_chk)
        g_layout.addRow(self.click_through_chk)
        g_layout.addRow(self.spontaneous_talk_chk)
        g_layout.addRow(self.autostart_chk)
        g_layout.addRow(self.nerd_mode_chk)
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
        self.ai_model_input = QLineEdit(self.settings.get("ai_model", "meta/llama-3.1-8b-instruct"))
        self.ai_model_input.setPlaceholderText("ex: meta/llama-3.1-8b-instruct ou gpt-4o-mini")
        self.ai_model_complex_input = QLineEdit(self.settings.get("ai_model_complex", "meta/llama-3.1-70b-instruct"))
        self.ai_model_complex_input.setPlaceholderText("ex: meta/llama-3.1-70b-instruct ou gpt-4o")
        self.ai_model_complex_input.setToolTip(
            "Usado só em perguntas que parecem precisar de mais raciocínio (explicações, "
            "comparações, perguntas longas) — mais lento, porém mais preciso e coerente do "
            "que o modelo rápido padrão."
        )
        ai_layout.addRow("Provedor de IA:", self.ai_combo)
        ai_layout.addRow("API Key:", self.api_key_input)
        ai_layout.addRow("Modelo (rápido):", self.ai_model_input)
        ai_layout.addRow("Modelo (perguntas complexas):", self.ai_model_complex_input)
        tabs.addTab(ai_tab, "IA")

        # Tab 3: Voz
        voice_tab = QWidget()
        voice_layout = QFormLayout(voice_tab)
        self.mic_chk = QCheckBox("Ativar Microfone (Push-to-Talk F8 / Mãos-Livres +)")
        self.mic_chk.setChecked(self.settings.get("microphone_enabled", False))
        self.whisper_model_combo = QComboBox()
        self.whisper_model_combo.addItems(["tiny", "base", "small", "medium"])
        self.whisper_model_combo.setCurrentText(self.settings.get("whisper_model", "small"))
        self.whisper_model_combo.setToolTip(
            "Modelos maiores reconhecem a fala com mais precisão, mas demoram mais\n"
            "e baixam mais dados na primeira vez. Requer reiniciar o app."
        )
        self.voice_gender_combo = QComboBox()
        self.voice_gender_combo.addItems([label for label, _ in VOICE_OPTIONS])
        current_voice = self.settings.get("voice", "pt-BR-AntonioNeural")
        for label, voice_name in VOICE_OPTIONS:
            if voice_name == current_voice:
                self.voice_gender_combo.setCurrentText(label)
                break
        self.voice_pitch_spin = QSpinBox()
        self.voice_pitch_spin.setRange(-50, 100)
        self.voice_pitch_spin.setSuffix(" Hz")
        self.voice_pitch_spin.setValue(_pitch_str_to_hz(self.settings.get("voice_pitch", "+20Hz")))
        self.voice_pitch_spin.setToolTip("Tom da voz — valores mais altos deixam a fala mais aguda/gatuna.")

        voice_layout.addRow(self.mic_chk)
        voice_layout.addRow("Precisão do Reconhecimento de Voz:", self.whisper_model_combo)
        voice_layout.addRow("Voz do Personagem:", self.voice_gender_combo)
        voice_layout.addRow("Tom da Voz:", self.voice_pitch_spin)
        tabs.addTab(voice_tab, "Voz")

        # Tab 4: Visão de Tela
        vision_tab = QWidget()
        v_layout = QFormLayout(vision_tab)
        self.vision_chk = QCheckBox("Ativar Visão de Tela (Screen Vision)")
        self.vision_chk.setChecked(self.settings.get("screen_monitoring_enabled", False))
        self.private_mode_chk = QCheckBox("Modo Privado (Nenhuma captura ou OCR)")
        self.private_mode_chk.setChecked(self.settings.get("private_mode", True))
        self.ai_vision_model_input = QLineEdit(self.settings.get("ai_vision_model", "meta/llama-3.2-11b-vision-instruct"))
        self.ai_vision_model_input.setPlaceholderText("ex: meta/llama-3.2-11b-vision-instruct ou gpt-4o-mini")
        self.ai_vision_model_input.setToolTip(
            "Modelo usado só nas mensagens sobre a tela. Fica separado do modelo de\n"
            "texto principal porque modelos de visão menores seguem instruções pior."
        )
        v_layout.addRow(self.vision_chk)
        v_layout.addRow(self.private_mode_chk)
        v_layout.addRow("Modelo de Visão:", self.ai_vision_model_input)
        tabs.addTab(vision_tab, "Visão")

        # Tab 5: Aplicativos (allowlist) — só apps aqui podem ser abertos/fechados
        # por comando de voz/texto (segurança: sem shell livre, sem allowlist não roda).
        apps_tab = QWidget()
        apps_layout = QVBoxLayout(apps_tab)
        apps_layout.addWidget(QLabel(
            "Apps que a Silva pode abrir/fechar por voz ou texto. Só o que estiver\n"
            "nesta lista funciona — é a proteção contra abrir qualquer coisa no PC."
        ))
        self.allowlist = dict(self.settings.get("allowlist", {}))
        self.app_list = QListWidget()
        self._refresh_app_list()
        apps_layout.addWidget(self.app_list)

        add_row = QHBoxLayout()
        self.app_name_input = QLineEdit()
        self.app_name_input.setPlaceholderText("nome (ex: firefox)")
        self.app_path_input = QLineEdit()
        self.app_path_input.setPlaceholderText("caminho do .exe")
        browse_btn = QPushButton("Procurar...")
        browse_btn.clicked.connect(self._browse_for_app_path)
        add_btn = QPushButton("Adicionar")
        add_btn.clicked.connect(self._add_app_to_allowlist)
        add_row.addWidget(self.app_name_input)
        add_row.addWidget(self.app_path_input)
        add_row.addWidget(browse_btn)
        add_row.addWidget(add_btn)
        apps_layout.addLayout(add_row)

        remove_btn = QPushButton("Remover selecionado")
        remove_btn.clicked.connect(self._remove_selected_app)
        apps_layout.addWidget(remove_btn)
        tabs.addTab(apps_tab, "Aplicativos")

        layout.addWidget(tabs)

        save_btn = QPushButton("Salvar Configurações")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _refresh_app_list(self):
        self.app_list.clear()
        for name, path in sorted(self.allowlist.items()):
            item = QListWidgetItem(f"{name} → {path}")
            item.setData(Qt.UserRole, name)
            self.app_list.addItem(item)

    def _browse_for_app_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecione o executável", "", "Executáveis (*.exe)")
        if path:
            self.app_path_input.setText(path)

    def _add_app_to_allowlist(self):
        name = self.app_name_input.text().strip().lower()
        path = self.app_path_input.text().strip()
        if not name or not path:
            QMessageBox.warning(self, "Aplicativos", "Preencha o nome e o caminho do executável.")
            return
        self.allowlist[name] = path
        self._refresh_app_list()
        self.app_name_input.clear()
        self.app_path_input.clear()

    def _remove_selected_app(self):
        item = self.app_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        self.allowlist.pop(name, None)
        self._refresh_app_list()

    def _save(self):
        self.settings.set("character_name", self.name_input.text().strip())
        self.settings.set("always_on_top", self.always_on_top_chk.isChecked())
        self.settings.set("click_through", self.click_through_chk.isChecked())
        self.settings.set("spontaneous_talk_enabled", self.spontaneous_talk_chk.isChecked())
        self.settings.set("autostart_enabled", self.autostart_chk.isChecked())
        autostart.set_enabled(self.autostart_chk.isChecked())
        self.settings.set("nerd_mode_enabled", self.nerd_mode_chk.isChecked())
        self.settings.set("ai_provider", self.ai_combo.currentText())
        self.settings.set("api_key", self.api_key_input.text().strip())
        self.settings.set("ai_model", self.ai_model_input.text().strip())
        self.settings.set("ai_model_complex", self.ai_model_complex_input.text().strip())
        self.settings.set("microphone_enabled", self.mic_chk.isChecked())
        self.settings.set("whisper_model", self.whisper_model_combo.currentText())
        selected_label = self.voice_gender_combo.currentText()
        voice_name = next((v for label, v in VOICE_OPTIONS if label == selected_label), "pt-BR-AntonioNeural")
        self.settings.set("voice", voice_name)
        pitch_value = self.voice_pitch_spin.value()
        self.settings.set("voice_pitch", f"{'+' if pitch_value >= 0 else ''}{pitch_value}Hz")
        self.settings.set("screen_monitoring_enabled", self.vision_chk.isChecked())
        self.settings.set("private_mode", self.private_mode_chk.isChecked())
        self.settings.set("ai_vision_model", self.ai_vision_model_input.text().strip())
        self.settings.set("allowlist", self.allowlist)
        if self.permission_manager is not None:
            self.permission_manager.allowlist.clear()
            self.permission_manager.allowlist.update(self.allowlist)
        self.close()
