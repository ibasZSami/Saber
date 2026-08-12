from src.voice.vad_segmenter import SpeechSegmenter


def _seg(rms_threshold=500, silence_duration_s=0.8, max_utterance_s=15):
    return SpeechSegmenter(rms_threshold, silence_duration_s, max_utterance_s)


class TestSpeechSegmenter:
    def test_silence_produces_no_utterance(self):
        seg = _seg()
        assert seg.push("chunk", rms=10, now=0.0) is None
        assert seg.is_speaking is False

    def test_speech_starts_but_does_not_finish_yet(self):
        seg = _seg()
        assert seg.push("chunk1", rms=1000, now=0.0) is None
        assert seg.is_speaking is True

    def test_silence_after_speech_below_duration_does_not_finish(self):
        seg = _seg(silence_duration_s=0.8)
        seg.push("speech", rms=1000, now=0.0)
        result = seg.push("silence", rms=10, now=0.5)
        assert result is None
        assert seg.is_speaking is True

    def test_silence_past_duration_finishes_utterance(self):
        """silence_start is stamped on the FIRST quiet chunk, so the duration is
        measured from there — a later chunk has to actually arrive after the
        threshold elapses (matches the original hand-rolled loop's behavior)."""
        seg = _seg(silence_duration_s=0.8)
        seg.push("speech1", rms=1000, now=0.0)
        seg.push("speech2", rms=1000, now=0.1)
        assert seg.push("silence1", rms=10, now=1.0) is None  # starts the silence timer
        result = seg.push("silence2", rms=10, now=1.9)  # 0.9s since silence started
        assert result == ["speech1", "speech2", "silence1", "silence2"]
        assert seg.is_speaking is False

    def test_max_duration_timeout_finishes_on_next_quiet_chunk(self):
        """The timeout is only evaluated on a below-threshold chunk (matches the
        original loop's structure exactly) — continuous loud audio past
        max_utterance_s doesn't cut off until a quiet chunk finally arrives."""
        seg = _seg(max_utterance_s=15, silence_duration_s=0.8)
        seg.push("speech1", rms=1000, now=0.0)
        assert seg.push("speech2", rms=1000, now=16.0) is None
        result = seg.push("silence", rms=10, now=16.1)
        assert result == ["speech1", "speech2", "silence"]
        assert seg.is_speaking is False

    def test_new_utterance_can_start_after_one_finishes(self):
        seg = _seg(silence_duration_s=0.8)
        seg.push("a", rms=1000, now=0.0)
        seg.push("silence1", rms=10, now=1.0)
        seg.push("silence2", rms=10, now=1.9)  # finishes first utterance
        assert seg.push("b", rms=1000, now=2.0) is None
        assert seg.is_speaking is True

    def test_resets_buffer_on_new_speech_after_finished_utterance(self):
        seg = _seg(silence_duration_s=0.8)
        seg.push("a", rms=1000, now=0.0)
        seg.push("silence1", rms=10, now=1.0)
        seg.push("silence2", rms=10, now=1.9)
        seg.push("b", rms=1000, now=2.0)
        assert seg.push("silence3", rms=10, now=3.0) is None  # starts new silence timer
        result = seg.push("silence4", rms=10, now=3.9)
        assert result == ["b", "silence3", "silence4"]
