import json
from unittest.mock import MagicMock

from src.core.event_bus import EventBus
from src.vision.translation_engine import TranslationEngine


def _engine(ai_provider=None):
    bus = EventBus()
    bus.reset()
    return TranslationEngine(ai_provider or MagicMock(), bus), bus


class TestTranslateBatch:
    def test_translates_new_text_via_the_ai(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Você bem?"})
        engine, _ = _engine(ai_provider)

        result = engine.translate_batch(["You ok?"])

        assert result == {"You ok?": "Você bem?"}

    def test_sends_a_single_numbered_batch_for_multiple_texts(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Oi", "2": "Tchau"})
        engine, _ = _engine(ai_provider)

        result = engine.translate_batch(["Hi", "Bye"])

        assert result == {"Hi": "Oi", "Bye": "Tchau"}
        ai_provider.chat.assert_called_once()
        sent_prompt = ai_provider.chat.call_args[0][0]
        assert "1. Hi" in sent_prompt
        assert "2. Bye" in sent_prompt

    def test_second_call_with_same_text_never_calls_the_ai_again(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Olá"})
        engine, _ = _engine(ai_provider)

        engine.translate_batch(["Hello"])
        result = engine.translate_batch(["Hello"])

        ai_provider.chat.assert_called_once()
        assert result == {"Hello": "Olá"}

    def test_mixed_cached_and_new_text_only_sends_the_new_ones(self):
        ai_provider = MagicMock()
        ai_provider.chat.side_effect = [
            json.dumps({"1": "Olá"}),
            json.dumps({"1": "Tchau"}),
        ]
        engine, _ = _engine(ai_provider)
        engine.translate_batch(["Hello"])

        result = engine.translate_batch(["Hello", "Bye"])

        assert result == {"Hello": "Olá", "Bye": "Tchau"}
        second_call_prompt = ai_provider.chat.call_args_list[1][0][0]
        assert "Hello" not in second_call_prompt

    def test_duplicate_text_in_the_same_batch_is_only_sent_once(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Olá"})
        engine, _ = _engine(ai_provider)

        result = engine.translate_batch(["Hello", "Hello"])

        sent_prompt = ai_provider.chat.call_args[0][0]
        assert sent_prompt.count("Hello") == 1
        assert result == {"Hello": "Olá"}

    def test_malformed_ai_response_falls_back_to_original_text(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = "isso não é JSON"
        engine, _ = _engine(ai_provider)

        result = engine.translate_batch(["Hello"])

        assert result == {"Hello": "Hello"}

    def test_provider_exception_falls_back_to_original_text_not_raise(self):
        ai_provider = MagicMock()
        ai_provider.chat.side_effect = RuntimeError("network down")
        engine, _ = _engine(ai_provider)

        result = engine.translate_batch(["Hello"])  # must not raise

        assert result == {"Hello": "Hello"}

    def test_empty_batch_returns_empty_and_does_not_call_the_ai(self):
        ai_provider = MagicMock()
        engine, _ = _engine(ai_provider)

        result = engine.translate_batch([])

        assert result == {}
        ai_provider.chat.assert_not_called()


class TestCached:
    def test_returns_none_for_untranslated_text(self):
        engine, _ = _engine()
        assert engine.cached("Hello") is None

    def test_returns_the_cached_translation(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Olá"})
        engine, _ = _engine(ai_provider)
        engine.translate_batch(["Hello"])
        assert engine.cached("Hello") == "Olá"


class TestClearCache:
    def test_clear_cache_forces_a_re_translation(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Olá"})
        engine, _ = _engine(ai_provider)
        engine.translate_batch(["Hello"])

        engine.clear_cache()
        engine.translate_batch(["Hello"])

        assert ai_provider.chat.call_count == 2


class TestEventEmission:
    def test_emits_translation_batch_completed_with_counts(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Olá"})
        engine, bus = _engine(ai_provider)
        engine.translate_batch(["Hello"])  # primes the cache
        received = []
        bus.subscribe("TRANSLATION_BATCH_COMPLETED", lambda **kw: received.append(kw))

        engine.translate_batch(["Hello", "New text"])

        assert len(received) == 1
        assert received[0]["total"] == 2
        assert received[0]["from_cache"] == 1
        assert received[0]["translated"] == 1
        assert received[0]["duration_seconds"] >= 0


class TestTranslateBatchAsync:
    def test_calls_on_done_with_the_result_off_the_calling_thread(self):
        ai_provider = MagicMock()
        ai_provider.chat.return_value = json.dumps({"1": "Olá"})
        engine, _ = _engine(ai_provider)
        done = {}
        event = __import__("threading").Event()

        def _on_done(result):
            done.update(result)
            event.set()

        engine.translate_batch_async(["Hello"], _on_done)
        event.wait(timeout=5)

        assert done == {"Hello": "Olá"}

    def test_on_done_still_called_when_translation_crashes(self):
        ai_provider = MagicMock()
        ai_provider.chat.side_effect = RuntimeError("boom")
        engine, _ = _engine(ai_provider)
        done = {}
        event = __import__("threading").Event()

        def _on_done(result):
            done.update(result)
            event.set()

        engine.translate_batch_async(["Hello"], _on_done)
        event.wait(timeout=5)

        assert done == {"Hello": "Hello"}
