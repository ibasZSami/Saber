"""Translation Mode — FASE 7. Ties together ScreenCapture, structured OCR
(src/vision/ocr.py's extract_structured, FASE 4), TranslationEngine (FASE
5), and OverlayWindow (FASE 6) into a continuous loop:

    captura -> diff contra o frame anterior -> se mudou: OCR -> traduzir
    (só o que não está em cache) -> atualizar overlay -> repetir

A QTimer drives the tick on the GUI thread; the translation call itself
runs async (TranslationEngine.translate_batch_async) so a slow AI response
never blocks the next capture. Its result comes back on a worker thread, so
it's routed through EventBus (TRANSLATION_BLOCKS_READY) rather than
touching the Qt overlay widget directly off-thread — same reasoning as
every other cross-thread Qt touch in this codebase (see event_bus.py)."""

import logging
from enum import Enum
from typing import Optional

from PySide6.QtCore import QTimer

from src.core.event_bus import EventBus, TRANSLATION_BLOCKS_READY, TRANSLATION_MODE_STATE_CHANGED
from src.ui.overlay_window import OverlayBlock, OverlayWindow

DEFAULT_CHECK_INTERVAL_MS = 800
DEFAULT_MIN_CONFIDENCE = 30.0


class TranslationModeState(str, Enum):
    OFF = "OFF"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"


class TranslationMode:
    def __init__(
        self, screen_capture, change_detector, ocr_provider, translation_engine, event_bus: EventBus,
        overlay_window: Optional[OverlayWindow] = None, min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ):
        self.screen_capture = screen_capture
        # Deliberately its OWN ScreenChangeDetector instance, never shared
        # with CompanionOrchestrator's periodic vision-monitoring one — two
        # independent consumers polling the same stateful detector would
        # each reset/consume the other's "changed" signal.
        self.change_detector = change_detector
        self.ocr_provider = ocr_provider
        self.translation_engine = translation_engine
        self.event_bus = event_bus
        self.overlay_window = overlay_window or OverlayWindow()
        self.min_confidence = min_confidence
        self.state = TranslationModeState.OFF
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self.event_bus.subscribe(TRANSLATION_BLOCKS_READY, self._apply_blocks)

    def _set_state(self, new_state: TranslationModeState):
        self.state = new_state
        self.event_bus.emit(TRANSLATION_MODE_STATE_CHANGED, state=new_state.value)

    def start(self, interval_ms: int = DEFAULT_CHECK_INTERVAL_MS):
        if self.state in (TranslationModeState.STARTING, TranslationModeState.RUNNING):
            return
        self._set_state(TranslationModeState.STARTING)
        self.overlay_window.show()
        self._timer.start(interval_ms)
        self._set_state(TranslationModeState.RUNNING)

    def stop(self):
        if self.state == TranslationModeState.OFF:
            return
        self._set_state(TranslationModeState.STOPPING)
        self._timer.stop()
        self.overlay_window.clear()
        self.overlay_window.hide()
        self._set_state(TranslationModeState.OFF)

    def _tick(self):
        try:
            img = self.screen_capture.capture_primary()
            if not self.change_detector.has_changed(img):
                return
            blocks = self.ocr_provider.extract_structured(img, min_confidence=self.min_confidence)
            if not blocks:
                self.overlay_window.clear()
                return
            texts = [b.text for b in blocks]
            self.translation_engine.translate_batch_async(
                texts, lambda translated: self._on_translated(blocks, translated),
            )
        except Exception as e:
            logging.error(f"Translation Mode tick failed: {e}")

    def _on_translated(self, blocks, translated: dict):
        # Runs on the TranslationEngine worker thread — hand off to the GUI
        # thread via EventBus instead of touching overlay_window here.
        overlay_blocks = [
            OverlayBlock(text=translated.get(b.text, b.text), x=b.x, y=b.y, width=b.width, height=b.height)
            for b in blocks
        ]
        self.event_bus.emit(TRANSLATION_BLOCKS_READY, blocks=overlay_blocks)

    def _apply_blocks(self, blocks):
        self.overlay_window.set_blocks(blocks)
