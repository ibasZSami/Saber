import sys
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMenu
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QPixmap, QMouseEvent, QContextMenuEvent

from src.character.animation_manager import AnimationManager
from src.character.state_manager import CharacterStateManager

class PetWindow(QWidget):
    def __init__(self, animation_manager: AnimationManager, state_manager: CharacterStateManager, click_through: bool = False):
        super().__init__()
        self.animation_manager = animation_manager
        self.state_manager = state_manager
        self.drag_position = QPoint()

        # Frameless, transparent background & always on top
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if click_through:
            flags |= Qt.WindowTransparentForInput

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.label)

        # Timer for animation update
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(1000 // max(1, self.animation_manager.default_fps))

        # Position at bottom-right of primary screen
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.resize(300, 300)
        self.move(screen.width() - 350, screen.height() - 400)

    def set_click_through(self, enabled: bool):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if enabled:
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.show()

    def _update_frame(self):
        pixmap = self.animation_manager.update()
        if pixmap and not pixmap.isNull():
            # Scale pixmap smoothly so sprite is clearly visible
            scaled = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(scaled)


    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.state_manager.set_state("INTERACTION", reason="Clicked by user")
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.state_manager.set_state("HAPPY", reason="Double clicked")
            # Signal parent orchestrator to open chat
            if hasattr(self, "on_double_click"):
                self.on_double_click()
