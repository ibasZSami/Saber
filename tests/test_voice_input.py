from unittest.mock import patch, MagicMock

import numpy as np

from src.voice.input import VoiceInput, SAMPLE_RATE


class TestVoiceInputLifecycle:
    def test_stop_without_start_is_noop(self):
        vi = VoiceInput()
        vi.stop_listening()
        assert vi.is_listening is False

    @patch("sounddevice.InputStream")
    def test_start_listening_sets_flag_and_starts_stream(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream

        vi = VoiceInput()
        vi.start_listening()

        assert vi.is_listening is True
        mock_stream.start.assert_called_once()

    @patch("sounddevice.InputStream")
    def test_start_listening_twice_is_idempotent(self, mock_stream_cls):
        mock_stream_cls.return_value = MagicMock()
        vi = VoiceInput()
        vi.start_listening()
        vi.start_listening()
        assert mock_stream_cls.call_count == 1

    @patch("sounddevice.InputStream")
    def test_stop_listening_closes_stream_and_clears_flag(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        vi = VoiceInput()
        vi.start_listening()
        vi.stop_listening()

        assert vi.is_listening is False
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_listening_started_signal_emits_on_start(self):
        with patch("sounddevice.InputStream", return_value=MagicMock()):
            vi = VoiceInput()
            received = []
            vi.listening_started.connect(lambda: received.append(True))
            vi.start_listening()
            assert received == [True]


class TestHandsFreeMode:
    def test_start_listening_ignored_while_hands_free_active(self):
        """Push-to-Talk (F8) and hands-free both open a mic InputStream — they
        must not run concurrently, or `_frames` bookkeeping would race."""
        vi = VoiceInput()
        vi.hands_free_enabled = True
        with patch("sounddevice.InputStream") as mock_stream_cls:
            vi.start_listening()
            mock_stream_cls.assert_not_called()
        assert vi.is_listening is False

    def test_set_hands_free_true_emits_signal_and_sets_flag(self):
        with patch("sounddevice.InputStream", return_value=MagicMock()):
            vi = VoiceInput()
            received = []
            vi.hands_free_toggled.connect(lambda enabled: received.append(enabled))
            try:
                vi.set_hands_free(True)
                assert vi.hands_free_enabled is True
                assert received == [True]
            finally:
                vi.set_hands_free(False)

    def test_set_hands_free_false_when_already_off_is_noop(self):
        vi = VoiceInput()
        received = []
        vi.hands_free_toggled.connect(lambda enabled: received.append(enabled))
        vi.set_hands_free(False)
        assert received == []

    def test_set_hands_free_true_when_already_on_is_noop(self):
        with patch("sounddevice.InputStream", return_value=MagicMock()):
            vi = VoiceInput()
            try:
                vi.set_hands_free(True)
                received = []
                vi.hands_free_toggled.connect(lambda enabled: received.append(enabled))
                vi.set_hands_free(True)
                assert received == []
            finally:
                vi.set_hands_free(False)

    def test_set_hands_free_toggles_back_off(self):
        with patch("sounddevice.InputStream", return_value=MagicMock()):
            vi = VoiceInput()
            vi.set_hands_free(True)
            vi.set_hands_free(False)
            assert vi.hands_free_enabled is False

    def test_missing_dependency_disables_hands_free_gracefully(self):
        vi = VoiceInput()
        failed = []
        vi.transcription_failed.connect(lambda reason: failed.append(reason))

        with patch.dict("sys.modules", {"sounddevice": None}):
            vi.set_hands_free(True)

        assert vi.hands_free_enabled is False
        assert len(failed) == 1


class TestVoiceInputTranscription:
    def test_transcribe_emits_signal_with_text(self):
        vi = VoiceInput()
        fake_segment = MagicMock()
        fake_segment.text = " olá mundo "
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_segment], None)
        vi._model = fake_model

        received = []
        failed = []
        vi.speech_recognized.connect(lambda text: received.append(text))
        vi.transcription_failed.connect(lambda reason: failed.append(reason))

        frames = [np.zeros((1600, 1), dtype=np.int16) for _ in range(5)]
        vi._transcribe(frames)

        assert received == ["olá mundo"]
        assert failed == []

    def test_transcribe_uses_accuracy_decoding_params(self):
        """Regression test: vad_filter + temperature=0 + condition_on_previous_text=False
        were added to cut down on mis-heard words and hallucinated repeats."""
        vi = VoiceInput()
        fake_segment = MagicMock()
        fake_segment.text = "oi"
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_segment], None)
        vi._model = fake_model

        frames = [np.zeros((SAMPLE_RATE, 1), dtype=np.int16)]
        vi._transcribe(frames)

        _, kwargs = fake_model.transcribe.call_args
        assert kwargs["vad_filter"] is True
        assert kwargs["temperature"] == 0.0
        assert kwargs["condition_on_previous_text"] is False
        assert kwargs["beam_size"] >= 1

    def test_transcribe_emits_failure_when_no_frames(self):
        vi = VoiceInput()
        vi._model = MagicMock()
        received, failed = [], []
        vi.speech_recognized.connect(lambda text: received.append(text))
        vi.transcription_failed.connect(lambda reason: failed.append(reason))

        vi._transcribe([])

        assert received == []
        assert len(failed) == 1
        vi._model.transcribe.assert_not_called()

    def test_transcribe_emits_failure_for_short_audio_without_loading_model(self):
        """Short taps (< MIN_AUDIO_SECONDS) must be rejected BEFORE touching the model,
        so a quick accidental F8 tap doesn't trigger a slow (or network-bound) model load."""
        vi = VoiceInput()
        received, failed = [], []
        vi.speech_recognized.connect(lambda text: received.append(text))
        vi.transcription_failed.connect(lambda reason: failed.append(reason))

        with patch.object(vi, "_ensure_model") as mock_ensure_model:
            frames = [np.zeros((100, 1), dtype=np.int16)]  # well under 0.3s
            vi._transcribe(frames)
            mock_ensure_model.assert_not_called()

        assert received == []
        assert len(failed) == 1
        assert "curta" in failed[0].lower()

    def test_transcribe_emits_failure_when_model_unavailable(self):
        vi = VoiceInput()
        vi._model_load_failed = True
        received, failed = [], []
        vi.speech_recognized.connect(lambda text: received.append(text))
        vi.transcription_failed.connect(lambda reason: failed.append(reason))

        frames = [np.zeros((SAMPLE_RATE, 1), dtype=np.int16)]
        vi._transcribe(frames)

        assert received == []
        assert len(failed) == 1

    def test_transcribe_emits_failure_when_all_segments_blank(self):
        vi = VoiceInput()
        fake_segment = MagicMock()
        fake_segment.text = "   "
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_segment], None)
        vi._model = fake_model

        received, failed = [], []
        vi.speech_recognized.connect(lambda text: received.append(text))
        vi.transcription_failed.connect(lambda reason: failed.append(reason))

        frames = [np.zeros((SAMPLE_RATE, 1), dtype=np.int16)]
        vi._transcribe(frames)

        assert received == []
        assert len(failed) == 1

    def test_transcribe_emits_failure_on_model_exception(self):
        vi = VoiceInput()
        fake_model = MagicMock()
        fake_model.transcribe.side_effect = RuntimeError("boom")
        vi._model = fake_model

        failed = []
        vi.transcription_failed.connect(lambda reason: failed.append(reason))

        frames = [np.zeros((SAMPLE_RATE, 1), dtype=np.int16)]
        vi._transcribe(frames)

        assert len(failed) == 1


class TestModelWarmUp:
    def test_ensure_model_caches_after_first_success(self):
        vi = VoiceInput()
        fake_model_instance = MagicMock()
        with patch("faster_whisper.WhisperModel", return_value=fake_model_instance) as mock_cls:
            first = vi._ensure_model()
            second = vi._ensure_model()

        assert first is fake_model_instance
        assert second is fake_model_instance
        mock_cls.assert_called_once()

    def test_ensure_model_marks_failed_after_exception_and_does_not_retry(self):
        vi = VoiceInput()
        with patch("faster_whisper.WhisperModel", side_effect=RuntimeError("no internet")) as mock_cls:
            first = vi._ensure_model()
            second = vi._ensure_model()

        assert first is None
        assert second is None
        mock_cls.assert_called_once()  # second call shouldn't retry a known-bad load

    def test_default_model_size_is_small(self):
        """Regression test: default used to be 'tiny', which mis-heard words often
        enough that the user asked for a more accurate model."""
        vi = VoiceInput()
        assert vi.model_size == "small"

    def test_custom_model_size_is_used_when_loading(self):
        vi = VoiceInput(model_size="medium")
        with patch("faster_whisper.WhisperModel") as mock_cls:
            vi._ensure_model()
        mock_cls.assert_called_once_with("medium", device="cpu", compute_type="int8")
