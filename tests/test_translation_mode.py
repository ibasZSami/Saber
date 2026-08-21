from unittest.mock import MagicMock

from src.core.event_bus import EventBus
from src.core.translation_mode import TranslationMode, TranslationModeState
from src.ui.overlay_window import OverlayBlock
from src.vision.ocr import TextBlock


def _mode(**overrides):
    bus = EventBus()
    bus.reset()
    screen_capture = overrides.get("screen_capture", MagicMock())
    change_detector = overrides.get("change_detector", MagicMock())
    ocr_provider = overrides.get("ocr_provider", MagicMock())
    translation_engine = overrides.get("translation_engine", MagicMock())
    overlay_window = overrides.get("overlay_window", MagicMock())
    mode = TranslationMode(
        screen_capture, change_detector, ocr_provider, translation_engine, bus, overlay_window=overlay_window,
    )
    return mode, bus


class TestStateMachine:
    def test_starts_off(self):
        mode, _ = _mode()
        assert mode.state == TranslationModeState.OFF

    def test_start_transitions_to_running_and_shows_overlay(self):
        mode, _ = _mode()
        mode.start()
        assert mode.state == TranslationModeState.RUNNING
        mode.overlay_window.show.assert_called_once()

    def test_start_emits_all_transition_states_in_order(self):
        mode, bus = _mode()
        received = []
        bus.subscribe("TRANSLATION_MODE_STATE_CHANGED", lambda **kw: received.append(kw["state"]))
        mode.start()
        assert received == ["STARTING", "RUNNING"]

    def test_starting_twice_is_a_no_op(self):
        mode, bus = _mode()
        mode.start()
        received = []
        bus.subscribe("TRANSLATION_MODE_STATE_CHANGED", lambda **kw: received.append(kw["state"]))
        mode.start()
        assert received == []

    def test_stop_transitions_back_to_off_and_hides_overlay(self):
        mode, _ = _mode()
        mode.start()
        mode.stop()
        assert mode.state == TranslationModeState.OFF
        mode.overlay_window.clear.assert_called_once()
        mode.overlay_window.hide.assert_called_once()

    def test_stop_emits_all_transition_states_in_order(self):
        mode, bus = _mode()
        mode.start()
        received = []
        bus.subscribe("TRANSLATION_MODE_STATE_CHANGED", lambda **kw: received.append(kw["state"]))
        mode.stop()
        assert received == ["STOPPING", "OFF"]

    def test_stopping_when_already_off_is_a_no_op(self):
        mode, bus = _mode()
        received = []
        bus.subscribe("TRANSLATION_MODE_STATE_CHANGED", lambda **kw: received.append(kw["state"]))
        mode.stop()
        assert received == []


class TestTick:
    def test_no_change_skips_ocr_entirely(self):
        change_detector = MagicMock()
        change_detector.has_changed.return_value = False
        ocr_provider = MagicMock()
        mode, _ = _mode(change_detector=change_detector, ocr_provider=ocr_provider)

        mode._tick()

        ocr_provider.extract_structured.assert_not_called()

    def test_change_with_no_text_clears_the_overlay(self):
        change_detector = MagicMock()
        change_detector.has_changed.return_value = True
        ocr_provider = MagicMock()
        ocr_provider.extract_structured.return_value = []
        mode, _ = _mode(change_detector=change_detector, ocr_provider=ocr_provider)

        mode._tick()

        mode.overlay_window.clear.assert_called_once()

    def test_change_with_text_starts_an_async_translation(self):
        change_detector = MagicMock()
        change_detector.has_changed.return_value = True
        ocr_provider = MagicMock()
        ocr_provider.extract_structured.return_value = [
            TextBlock(text="You ok?", x=10, y=20, width=50, height=15, confidence=90.0),
        ]
        translation_engine = MagicMock()
        mode, _ = _mode(change_detector=change_detector, ocr_provider=ocr_provider, translation_engine=translation_engine)

        mode._tick()

        translation_engine.translate_batch_async.assert_called_once()
        call_args = translation_engine.translate_batch_async.call_args[0]
        assert call_args[0] == ["You ok?"]

    def test_exception_during_tick_does_not_propagate(self):
        change_detector = MagicMock()
        change_detector.has_changed.side_effect = RuntimeError("boom")
        mode, _ = _mode(change_detector=change_detector)

        mode._tick()  # should not raise


class TestTranslatedResultAppliedToOverlay:
    def test_on_translated_emits_translation_blocks_ready(self):
        mode, bus = _mode()
        received = []
        bus.subscribe("TRANSLATION_BLOCKS_READY", lambda **kw: received.append(kw))
        blocks = [TextBlock(text="You ok?", x=10, y=20, width=50, height=15, confidence=90.0)]

        mode._on_translated(blocks, {"You ok?": "Você bem?"})

        assert len(received) == 1
        overlay_blocks = received[0]["blocks"]
        assert overlay_blocks == [OverlayBlock(text="Você bem?", x=10, y=20, width=50, height=15)]

    def test_missing_translation_falls_back_to_original_text(self):
        mode, bus = _mode()
        received = []
        bus.subscribe("TRANSLATION_BLOCKS_READY", lambda **kw: received.append(kw))
        blocks = [TextBlock(text="Untranslated", x=0, y=0, width=1, height=1, confidence=90.0)]

        mode._on_translated(blocks, {})

        assert received[0]["blocks"][0].text == "Untranslated"

    def test_apply_blocks_updates_the_overlay_window(self):
        mode, _ = _mode()
        blocks = [OverlayBlock(text="Você bem?", x=10, y=20, width=50, height=15)]

        mode._apply_blocks(blocks)

        mode.overlay_window.set_blocks.assert_called_once_with(blocks)

    def test_translation_blocks_ready_event_reaches_the_overlay_end_to_end(self):
        """The real point of routing this through EventBus instead of a
        direct call — the emit from _on_translated (simulating the worker
        thread) must actually reach _apply_blocks (the GUI-thread slot)."""
        mode, bus = _mode()
        blocks = [TextBlock(text="You ok?", x=10, y=20, width=50, height=15, confidence=90.0)]

        mode._on_translated(blocks, {"You ok?": "Você bem?"})

        mode.overlay_window.set_blocks.assert_called_once()
        applied = mode.overlay_window.set_blocks.call_args[0][0]
        assert applied[0].text == "Você bem?"
