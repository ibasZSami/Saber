from unittest.mock import MagicMock, patch

import numpy as np

from src.voice.system_audio import SystemAudioListener, SAMPLE_RATE, CAPTURE_SAMPLE_RATE


def _fake_soundcard_module(loopback_mic):
    """Builds a minimal fake `soundcard` module: default_speaker() succeeds,
    get_microphone() returns the given (possibly None) loopback mic stand-in."""
    fake_speaker = MagicMock(name="fake_speaker_obj")
    fake_speaker.name = "Speakers"
    fake_sc = MagicMock()
    fake_sc.default_speaker.return_value = fake_speaker
    fake_sc.get_microphone.return_value = loopback_mic
    return fake_sc


class TestSetEnabledLifecycle:
    def test_set_enabled_false_when_already_off_is_noop(self):
        listener = SystemAudioListener()
        received = []
        listener.listening_toggled.connect(lambda enabled: received.append(enabled))

        listener.set_enabled(False)

        assert received == []
        assert listener.enabled is False

    def test_set_enabled_true_emits_toggled_true_on_success(self):
        listener = SystemAudioListener()
        fake_recorder_ctx = MagicMock()
        fake_recorder_ctx.__enter__.return_value.record.return_value = np.zeros((4800, 2), dtype="float32")
        loopback_mic = MagicMock(name="Speakers (loopback)")
        loopback_mic.recorder.return_value = fake_recorder_ctx
        fake_sc = _fake_soundcard_module(loopback_mic)

        with patch.dict("sys.modules", {"soundcard": fake_sc}):
            received = []
            listener.listening_toggled.connect(lambda enabled: received.append(enabled))
            listener.set_enabled(True)
            listener.set_enabled(False)  # cleanup: stop the background thread

        assert received[0] is True

    def test_set_enabled_true_emits_toggled_false_when_no_device_found(self):
        listener = SystemAudioListener()
        fake_sc = _fake_soundcard_module(loopback_mic=None)

        with patch.dict("sys.modules", {"soundcard": fake_sc}):
            received = []
            failed = []
            listener.listening_toggled.connect(lambda enabled: received.append(enabled))
            listener.transcription_failed.connect(lambda reason: failed.append(reason))

            listener.set_enabled(True)

        assert received == [False]
        assert listener.enabled is False
        assert len(failed) == 1

    def test_capture_failure_resets_enabled_so_it_can_restart(self):
        """Regression guard: if the capture thread dies mid-stream (device
        disconnected, driver error), `enabled` must go back to False — otherwise
        set_enabled(True)'s "already enabled" no-op check silently blocks any
        attempt to restart listening after the failure."""
        listener = SystemAudioListener()
        loopback_mic = MagicMock(name="Speakers (loopback)")
        loopback_mic.recorder.side_effect = RuntimeError("device gone")
        fake_sc = _fake_soundcard_module(loopback_mic)

        with patch.dict("sys.modules", {"soundcard": fake_sc}):
            received = []
            listener.listening_toggled.connect(lambda enabled: received.append(enabled))
            listener.set_enabled(True)
            listener._thread.join(timeout=2)

        assert listener.enabled is False
        assert received[-1] is False

    def test_set_enabled_true_with_missing_dependency_fails_gracefully(self):
        listener = SystemAudioListener()
        failed = []
        listener.transcription_failed.connect(lambda reason: failed.append(reason))

        with patch.dict("sys.modules", {"soundcard": None}):
            listener.set_enabled(True)

        assert listener.enabled is False
        assert len(failed) == 1


class TestModelSharing:
    def test_uses_provided_model_provider_instead_of_loading_its_own(self):
        shared_model = MagicMock()
        listener = SystemAudioListener(model_provider=lambda: shared_model)

        assert listener._ensure_model() is shared_model

    def test_falls_back_to_own_model_when_no_provider_given(self):
        listener = SystemAudioListener(model_provider=None)
        fake_model_instance = MagicMock()

        with patch("faster_whisper.WhisperModel", return_value=fake_model_instance):
            model = listener._ensure_model()

        assert model is fake_model_instance


class TestResample:
    def test_no_resample_needed_when_already_16k(self):
        listener = SystemAudioListener()
        audio = np.zeros(1600, dtype=np.float32)

        result = listener._resample_to_16k(audio, SAMPLE_RATE)

        assert result is audio

    def test_resamples_to_target_length(self):
        listener = SystemAudioListener()
        one_second = np.zeros(CAPTURE_SAMPLE_RATE, dtype=np.float32)

        result = listener._resample_to_16k(one_second, CAPTURE_SAMPLE_RATE)

        assert abs(len(result) - SAMPLE_RATE) <= 1

    def test_resampled_output_is_float32(self):
        """Regression test: np.interp (used internally) always returns float64,
        but faster-whisper's ONNX VAD filter rejects anything but float32 and
        throws at transcribe time — this only ever showed up in a live run,
        not in mocked tests, so it's pinned here explicitly."""
        listener = SystemAudioListener()
        one_second = np.zeros(CAPTURE_SAMPLE_RATE, dtype=np.float32)

        result = listener._resample_to_16k(one_second, CAPTURE_SAMPLE_RATE)

        assert result.dtype == np.float32


class TestTranscribeFiltering:
    def _frames(self, seconds=1.0):
        return [np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32)]

    def test_discards_high_no_speech_prob_segments(self):
        """Regression guard: game/PC audio (music, effects) makes Whisper
        hallucinate text on non-speech; segments it flags as unlikely-speech
        must not reach the AI."""
        listener = SystemAudioListener()
        noisy_segment = MagicMock(text="ruído aleatório", no_speech_prob=0.95)
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([noisy_segment], None)
        listener._own_model = fake_model

        received = []
        listener.audio_transcribed.connect(lambda text: received.append(text))

        listener._transcribe(self._frames(), SAMPLE_RATE)

        assert received == []

    def test_emits_low_no_speech_prob_segments(self):
        listener = SystemAudioListener()
        speech_segment = MagicMock(text="cuidado, atrás de você!", no_speech_prob=0.1)
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([speech_segment], None)
        listener._own_model = fake_model

        received = []
        listener.audio_transcribed.connect(lambda text: received.append(text))

        listener._transcribe(self._frames(), SAMPLE_RATE)

        assert received == ["cuidado, atrás de você!"]

    def test_respects_emit_cooldown(self):
        """Continuous game audio rarely goes silent, so segmentation alone
        isn't enough to prevent spamming the AI with constant reactions."""
        listener = SystemAudioListener()
        segment = MagicMock(text="fala", no_speech_prob=0.1)
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([segment], None)
        listener._own_model = fake_model

        received = []
        listener.audio_transcribed.connect(lambda text: received.append(text))

        listener._transcribe(self._frames(), SAMPLE_RATE)
        listener._transcribe(self._frames(), SAMPLE_RATE)

        assert len(received) == 1

    def test_skips_too_short_audio(self):
        listener = SystemAudioListener()
        fake_model = MagicMock()
        listener._own_model = fake_model

        listener._transcribe(self._frames(seconds=0.05), SAMPLE_RATE)

        fake_model.transcribe.assert_not_called()
