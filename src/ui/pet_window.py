import logging
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent

from src.character.animation_manager import AnimationManager
from src.character.state_manager import CharacterStateManager
from src.core.event_bus import EventBus, USER_CLICKED_CHARACTER

BASE_WINDOW_SIZE = 300
# A fixed 300px window is fine on a big/high-res monitor, but on a small or
# heavily-scaled display (e.g. a laptop at ~1067x643 logical after 150% DPI
# scaling) it eats up nearly half the screen height — the corner-anchor math
# is still correct, but a window that large visually reads as "parked in the
# middle" instead of tucked into a corner. Capping it as a fraction of the
# screen's shorter side keeps it looking corner-docked on any display.
MAX_WINDOW_SIZE_SCREEN_FRACTION = 0.3
MIN_WINDOW_SIZE = 120

class PetWindow(QWidget):
    def __init__(self, animation_manager: AnimationManager, state_manager: CharacterStateManager, click_through: bool = False, window_margin_x: int = 40, window_margin_y: int = 40, scale: float = 1.0):
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

        screen = QApplication.primaryScreen().availableGeometry()
        max_size = int(min(screen.width(), screen.height()) * MAX_WINDOW_SIZE_SCREEN_FRACTION)
        # MIN_WINDOW_SIZE must be the actual floor of the final size, so it has
        # to apply AFTER scale — clamping before multiplying let a scale < 1.0
        # push the result back below the floor (scale=0.3 on a screen where
        # the pre-scale size was already at the 120px floor produced a 36px
        # window; scale=0 produced a 0px, fully invisible one).
        window_size = int(max(MIN_WINDOW_SIZE, min(BASE_WINDOW_SIZE, max_size) * scale))
        self._pixmap_size = int(window_size * (200 / BASE_WINDOW_SIZE))

        # A static pose per state, swapped only when the state actually changes
        # (no per-frame timer — see AnimationManager for why).
        self.animation_manager.frame_changed.connect(self._set_pixmap)
        self._set_pixmap(self.animation_manager.get_current_frame())

        # Anchor to the bottom-right corner using a margin from the real screen
        # edge (not a fixed absolute coordinate) — a fixed pixel target assumes
        # a specific resolution/DPI scale and lands wrong (e.g. mid-screen)
        # whenever the actual logical screen size differs.
        self.resize(window_size, window_size)
        self._target_x = max(0, screen.width() - self.width() - window_margin_x)
        self._target_y = max(0, screen.height() - self.height() - window_margin_y)
        self.move(self._target_x, self._target_y)
        self._positioned_after_show = False

    def showEvent(self, event):
        super().showEvent(event)
        # Frameless + WA_TranslucentBackground widgets on Windows don't always
        # honor move()/resize() called before the native HWND exists — the
        # native window can get created with a platform-default position once
        # show() actually maps it, silently discarding the pre-show placement
        # even though Qt's own pre-show geometry() accessors already reported
        # the (never-applied) target. Re-asserting the position here, once the
        # real window exists, is what actually sticks.
        if not self._positioned_after_show:
            self._positioned_after_show = True
            self.move(self._target_x, self._target_y)
            screen = QApplication.primaryScreen().availableGeometry()
            logging.info(
                f"PetWindow placement (post-show): screen={screen.width()}x{screen.height()} "
                f"devicePixelRatio={QApplication.primaryScreen().devicePixelRatio()} "
                f"target=({self._target_x},{self._target_y}) actual=({self.x()},{self.y()}) "
                f"frameGeometry={self.frameGeometry()}"
            )

    def set_click_through(self, enabled: bool):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if enabled:
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.show()

    def _set_pixmap(self, pixmap):
        if pixmap and not pixmap.isNull():
            # Scale pixmap smoothly so sprite is clearly visible
            scaled = pixmap.scaled(self._pixmap_size, self._pixmap_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
