"""Transparent translation overlay — FASE 6. A frameless, click-through,
always-on-top window drawn OVER whatever app is in the foreground, showing
translated text at the same position as the original instead of a separate
window competing for attention. Same Qt.WindowTransparentForInput approach
already used by PetWindow's click-through mode (src/ui/pet_window.py) —
proven in this codebase rather than a new WinAPI-level hack.

Known limitation, documented rather than hidden: an app running in true
EXCLUSIVE fullscreen (not borderless/windowed) owns the whole screen at the
driver level and nothing else can be composited over it — this only works
over windowed or borderless-fullscreen content. There is no portable
workaround for exclusive fullscreen short of hooking the game's own
renderer, well outside this project's scope."""

from dataclasses import dataclass
from typing import List

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QWidget

# Background box behind translated text — dark, mostly opaque, so the
# original text underneath stops being legible (the "cover the original"
# behavior from the spec) while still reading as an overlay.
BOX_BACKGROUND = QColor(20, 20, 20, 235)
TEXT_COLOR = QColor(255, 255, 255)
BOX_PADDING = 4
MIN_FONT_PT = 8.0
MAX_FONT_PT = 22.0


@dataclass(frozen=True)
class OverlayBlock:
    """Same coordinate space as src/vision/ocr.py's TextBlock — physical
    screen pixels, since both come from the same mss capture. OverlayWindow
    converts to Qt's logical coordinates internally (see _physical_to_logical)."""

    text: str
    x: int
    y: int
    width: int
    height: int


def _physical_to_logical(block: OverlayBlock, dpr: float) -> QRect:
    """Converts a physical-pixel OCR box into the logical-pixel rect Qt
    paints in, expanded by BOX_PADDING — DPI scaling means these differ
    (e.g. a 150%-scaled display has dpr=1.5, so a physical 300px box is a
    200px logical one)."""
    x, y = block.x / dpr, block.y / dpr
    w, h = block.width / dpr, block.height / dpr
    return QRect(
        int(x - BOX_PADDING), int(y - BOX_PADDING),
        int(w + BOX_PADDING * 2), int(h + BOX_PADDING * 2),
    )


def fit_font_size(text: str, box_width: float, box_height: float) -> float:
    """Shrinks the font until `text` fits the box, never below MIN_FONT_PT —
    a translation is often longer than the original (Portuguese tends to run
    longer than English), so this is what keeps it legible instead of
    silently overflowing its line. Pure/testable without a live QWidget."""
    size = MAX_FONT_PT
    while size > MIN_FONT_PT:
        metrics = QFontMetrics(_font(size))
        if metrics.horizontalAdvance(text) <= box_width and metrics.height() <= box_height * 1.5:
            break
        size -= 1.0
    return size


def _font(point_size: float) -> QFont:
    font = QFont()
    font.setPointSizeF(point_size)
    return font


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Showing the overlay must never steal focus from whatever app the
        # user is actually working in underneath.
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._blocks: List[OverlayBlock] = []
        self._dpr = 1.0
        self._positioned_after_show = False
        self._fit_to_primary_screen()

    def _fit_to_primary_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        self._dpr = screen.devicePixelRatio() or 1.0
        self.setGeometry(screen.geometry())

    def showEvent(self, event):
        super().showEvent(event)
        # Same known Windows quirk as PetWindow (see its showEvent): a
        # frameless + WA_TranslucentBackground window doesn't always honor
        # geometry set before the native HWND exists — re-asserting it here
        # is what actually sticks.
        if not self._positioned_after_show:
            self._positioned_after_show = True
            self._fit_to_primary_screen()

    def set_blocks(self, blocks: List[OverlayBlock]):
        self._blocks = blocks
        self.update()

    def clear(self):
        self.set_blocks([])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for block in self._blocks:
            self._paint_block(painter, block)
        painter.end()

    def _paint_block(self, painter: QPainter, block: OverlayBlock):
        rect = _physical_to_logical(block, self._dpr)
        painter.fillRect(rect, BOX_BACKGROUND)
        painter.setFont(_font(fit_font_size(block.text, rect.width(), rect.height())))
        painter.setPen(TEXT_COLOR)
        painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, block.text)
