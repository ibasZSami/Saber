import sys
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMenu, QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPixmap, QMouseEvent, QContextMenuEvent

from src.character.animation_manager import AnimationManager
from src.character.state_manager import CharacterStateManager
from src.core.event_bus import EventBus, USER_CLICKED_CHARACTER

class PetWindow(QWidget):
    def __init__(self, animation_manager: AnimationManager, state_manager: CharacterStateManager, click_through: bool = False, window_margin_x: int = 40, window_margin_y: int = 40):
        super().__init__()
        self.animation_manager = animation_manager
        self.state_manager = state_manager
        self.event_bus = EventBus()
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

        # A static pose per state, swapped only when the state actually changes
        # (no per-frame timer — see AnimationManager for why).
        self.animation_manager.frame_changed.connect(self._set_pixmap)
        self._set_pixmap(self.animation_manager.get_current_frame())

        # Anchor to the bottom-right corner using a margin from the real screen
        # edge (not a fixed absolute coordinate) — a fixed pixel target assumes
        # a specific resolution/DPI scale and lands wrong (e.g. mid-screen)
        # whenever the actual logical screen size differs.
        self.resize(300, 300)
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.width() - window_margin_x
        y = screen.height() - self.height() - window_margin_y
        self.move(max(0, x), max(0, y))

    def set_click_through(self, enabled: bool):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if enabled:
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.show()

    def _set_pixmap(self, pixmap):
        if pixmap and not pixmap.isNull():
            # Scale pixmap smoothly so sprite is clearly visible
            scaled = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(scaled)


    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.state_manager.set_state("INTERACTION", reason="Clicked by user")
            self.event_bus.emit(USER_CLICKED_CHARACTER, click_type="single")
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.state_manager.set_state("HAPPY", reason="Double clicked")
            self.event_bus.emit(USER_CLICKED_CHARACTER, click_type="double")
            # Signal parent orchestrator to open chat
            if hasattr(self, "on_double_click"):
                self.on_double_click()
