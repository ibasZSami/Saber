import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.config.settings import Settings
from src.core.orchestrator import CompanionOrchestrator
from src.ui.pet_window import PetWindow
from src.ui.chat_window import ChatWindow
from src.ui.settings_window import SettingsWindow
from src.ui.wizard import SetupWizard
from src.ui.tray import TrayIcon

def run_app():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    settings = Settings()

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
    orchestrator = CompanionOrchestrator(settings)

    # Pet Window
    pet_window = PetWindow(orchestrator.animation_manager, orchestrator.state_manager, settings.get("click_through", False))
    pet_window.show()
    pet_window.raise_()
    pet_window.activateWindow()

    # Chat Window
    chat_window = ChatWindow(settings.get("character_name", "Lumi"))
    chat_window.show()
    chat_window.raise_()
    chat_window.activateWindow()

    # Settings Window
    settings_window = SettingsWindow(settings)

    # Connect signals
    pet_window.on_double_click = lambda: (chat_window.show(), chat_window.raise_(), chat_window.activateWindow())
    chat_window.message_sent.connect(lambda msg: orchestrator.handle_user_message(msg, on_response=lambda res: chat_window.append_message(settings.get("character_name", "Lumi"), res)))

    # System Tray
    tray = TrayIcon(
        on_chat=lambda: (chat_window.show(), chat_window.raise_(), chat_window.activateWindow()),
        on_settings=lambda: (settings_window.show(), settings_window.raise_(), settings_window.activateWindow()),
        on_vision_toggle=lambda: orchestrator.set_vision_monitoring(not settings.get("screen_monitoring_enabled", False)),
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
    }


run_app = run_app
