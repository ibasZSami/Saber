import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.config.settings import Settings
from src.core import autostart
from src.core.orchestrator import CompanionOrchestrator
from src.core.event_bus import SPONTANEOUS_SPEECH, VISION_MONITORING_TOGGLED, APP_AUTO_RESOLVED
from src.ui.pet_window import PetWindow
from src.ui.chat_window import ChatWindow
from src.ui.settings_window import SettingsWindow
from src.ui.wizard import SetupWizard
from src.ui.tray import TrayIcon
from src.ui.confirmation_dialog import ConfirmationBridge, make_confirm_fn

def run_app():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    settings = Settings()

    # Reconciles the real Windows registry entry with the configured preference
    # on every launch — defaults to True, so a fresh install auto-starts without
    # the user having to open Settings and save once first. Also self-heals if
    # the registry entry is ever missing/removed some other way.
    desired_autostart = settings.get("autostart_enabled", True)
    if autostart.is_enabled() != desired_autostart:
        autostart.set_enabled(desired_autostart)

    # Always show wizard if no API key or show main app directly
    if not settings.get("api_key"):
        wizard = SetupWizard(settings)
        wizard.setWindowFlags(wizard.windowFlags() | Qt.WindowStaysOnTopHint)
        wizard.wizard_completed.connect(lambda: _start_main(app, settings))
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()
    else:
        _start_main(app, settings)

    sys.exit(app.exec())

def _start_main(app, settings):
    # Built before the orchestrator so its AgentCore can be wired with a real
    # confirm_fn from construction — CONFIRM-tier tools ask via a modal dialog
    # (blocking whichever worker thread called them, not the GUI) instead of
    # auto-approving. See src/ui/confirmation_dialog.py.
    confirmation_bridge = ConfirmationBridge()
    orchestrator = CompanionOrchestrator(settings, confirm_fn=make_confirm_fn(confirmation_bridge))

    # Pet Window
    pet_window = PetWindow(
        orchestrator.animation_manager,
        orchestrator.state_manager,
        settings.get("click_through", False),
        window_margin_x=settings.get("window_margin_x", 40),
        window_margin_y=settings.get("window_margin_y", 40),
        scale=settings.get("scale", 1.0),
    )
    pet_window.show()
    pet_window.raise_()
    pet_window.activateWindow()

    # Chat Window — created now (signals need wiring below) but not shown until
    # the user asks for it (double-click on the pet / tray menu). It used to
    # show()+activateWindow() unconditionally at startup, which stole focus
    # from the correctly bottom-right-anchored pet window and, since Qt gives
    # a freshly-created top-level widget no explicit position, appeared
    # centered on screen — that's what actually looked like "vem no meio da
    # tela", not the pet itself.
    chat_window = ChatWindow(settings.get("character_name", "Silva"))

    # Settings Window
    settings_window = SettingsWindow(
        settings, orchestrator.permission_manager, orchestrator.policy_manager, orchestrator.activity_log,
    )

    # Connect signals
    pet_window.on_double_click = lambda: (chat_window.show(), chat_window.raise_(), chat_window.activateWindow())
    chat_window.message_sent.connect(lambda msg: orchestrator.handle_user_message(msg, on_response=lambda res: chat_window.append_message(settings.get("character_name", "Silva"), res)))

    # Voice Input (Push-to-Talk F8)
    def _on_voice_transcribed(text):
        if not text:
            return
        chat_window.append_message("Você (voz)", text)
        orchestrator.handle_user_message(text, on_response=lambda res: chat_window.append_message(settings.get("character_name", "Silva"), res))

    orchestrator.voice_input.speech_recognized.connect(_on_voice_transcribed)
    orchestrator.voice_input.transcription_failed.connect(
        lambda reason: chat_window.append_message(settings.get("character_name", "Silva"), f"🎤 {reason}")
    )

    orchestrator.voice_input.hands_free_toggled.connect(
        lambda enabled: chat_window.append_message(
            settings.get("character_name", "Silva"),
            "🎤 Modo mãos-livres ativado — pode falar a qualquer momento." if enabled
            else "🎤 Modo mãos-livres desativado."
        )
    )

    if settings.get("microphone_enabled", False):
        try:
            import keyboard
            keyboard.on_press_key("f8", lambda e: orchestrator.voice_input.start_listening())
            keyboard.on_release_key("f8", lambda e: orchestrator.voice_input.stop_listening())
            keyboard.add_hotkey("+", lambda: orchestrator.voice_input.set_hands_free(not orchestrator.voice_input.hands_free_enabled))
            logging.info("Push-to-Talk (F8) e modo mãos-livres (+) registrados.")
        except Exception as e:
            logging.warning(f"Não foi possível registrar os atalhos globais de voz: {e}")

    # Tecla "-": liga/desliga a Visão de Tela permanentemente (independe do microfone).
    # "keyboard" trata "-" e "Ctrl+-" como atalhos independentes — sem esse guard,
    # apertar Ctrl+- dispara os dois ao mesmo tempo (visão E áudio do sistema).
    def _toggle_vision_unless_ctrl_held():
        import keyboard
        if keyboard.is_pressed("ctrl"):
            return
        orchestrator.set_full_vision(not settings.get("screen_monitoring_enabled", False))

    try:
        import keyboard
        keyboard.add_hotkey("-", _toggle_vision_unless_ctrl_held)
        logging.info("Atalho global '-' (Visão de Tela) registrado.")
    except Exception as e:
        logging.warning(f"Não foi possível registrar o atalho global '-': {e}")

    # Áudio do sistema (som do jogo/PC): "está ouvindo o som do jogo/pc" ou Ctrl+-
    def _on_system_audio_transcribed(text):
        if not text:
            return
        chat_window.append_message("🔊 Som do PC", text)
        orchestrator.handle_user_message(
            f"[Áudio do jogo/PC]: {text}",
            on_response=lambda res: chat_window.append_message(settings.get("character_name", "Silva"), res),
            # Overheard, not said to Silva — must not carry command authority
            # (toggling Nerd Mode, activating vision, etc.) the way real user
            # speech/text does. See handle_user_message's docstring.
            is_direct_input=False,
        )

    orchestrator.system_audio_listener.audio_transcribed.connect(_on_system_audio_transcribed)
    orchestrator.system_audio_listener.listening_toggled.connect(
        lambda enabled: chat_window.append_message(
            settings.get("character_name", "Silva"),
            "🔊 Ouvindo o som do jogo/PC." if enabled
            else "🔊 Parei de ouvir o som do jogo/PC."
        )
    )
    orchestrator.system_audio_listener.transcription_failed.connect(
        lambda reason: chat_window.append_message(settings.get("character_name", "Silva"), f"🔊 {reason}")
    )

    # Fala espontânea ("como numa chamada"): "pare de falar aleatoriamente" / "ativar falar aleatoriamente"
    orchestrator.event_bus.subscribe(
        SPONTANEOUS_SPEECH,
        lambda speech: chat_window.append_message(settings.get("character_name", "Silva"), speech)
    )

    # Visão de Tela: "-" / bandeja / "minha tela" chamam set_full_vision() direto,
    # sem passar por handle_user_message — sem isso, o toggle acontecia em silêncio.
    orchestrator.event_bus.subscribe(
        VISION_MONITORING_TOGGLED,
        lambda enabled: chat_window.append_message(
            settings.get("character_name", "Silva"),
            "👁️ Visão de Tela ativada." if enabled else "👁️ Visão de Tela desativada."
        )
    )

    # Abrir app fora da allowlist: resolvido só pra essa vez, não fica salvo —
    # avisa o usuário disso em vez de deixar acontecer em silêncio.
    orchestrator.event_bus.subscribe(
        APP_AUTO_RESOLVED,
        lambda app_name, command: chat_window.append_message(
            settings.get("character_name", "Silva"),
            f"🔓 Abri \"{app_name}\" (não estava nos aplicativos permitidos — resolvi essa vez só, "
            "não vou lembrar sozinha; adiciona em Configurações → Aplicativos se quiser)."
        )
    )

    try:
        import keyboard
        keyboard.add_hotkey(
            "ctrl+-",
            lambda: orchestrator.system_audio_listener.set_enabled(not orchestrator.system_audio_listener.enabled)
        )
        logging.info("Atalho global 'Ctrl+-' (Ouvir áudio do PC) registrado.")
    except Exception as e:
        logging.warning(f"Não foi possível registrar o atalho global 'Ctrl+-': {e}")

    # System Tray
    tray = TrayIcon(
        on_chat=lambda: (chat_window.show(), chat_window.raise_(), chat_window.activateWindow()),
        on_settings=lambda: (settings_window.show(), settings_window.raise_(), settings_window.activateWindow()),
        on_vision_toggle=lambda: orchestrator.set_full_vision(not settings.get("screen_monitoring_enabled", False)),
        on_exit=lambda: app.quit()
    )

    # Keep strong references alive for the lifetime of the app.
    # Without this, these objects (owned only by this function's locals)
    # get garbage-collected as soon as _start_main returns, which silently
    # kills the tray icon and can crash Qt when its C++ side outlives Python's.
    app._companion_refs = {
        "orchestrator": orchestrator,
        "pet_window": pet_window,
        "chat_window": chat_window,
        "settings_window": settings_window,
        "tray": tray,
        "confirmation_bridge": confirmation_bridge,
    }


run_app = run_app
