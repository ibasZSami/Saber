import sys
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter
from PySide6.QtCore import Qt

def create_dummy_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setBrush(QColor(158, 27, 50))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, 24, 24)
    painter.end()
    return QIcon(pixmap)

class TrayIcon(QSystemTrayIcon):
    def __init__(self, parent=None, on_chat=None, on_settings=None, on_vision_toggle=None, on_exit=None):
        super().__init__(create_dummy_icon(), parent)
        self.setToolTip("Shimeji AI Companion (Saber)")

        menu = QMenu()
        chat_act = menu.addAction("🔮 Conversar")
        if on_chat:
            chat_act.triggered.connect(on_chat)

        vision_act = menu.addAction("👁️ Alternar Visão de Tela")
        if on_vision_toggle:
            vision_act.triggered.connect(on_vision_toggle)

        settings_act = menu.addAction("⚙️ Configurações")
        if on_settings:
            settings_act.triggered.connect(on_settings)

        menu.addSeparator()
        exit_act = menu.addAction("❌ Sair")
        if on_exit:
            exit_act.triggered.connect(on_exit)

        self.setContextMenu(menu)
        self.show()
