from unittest.mock import MagicMock, AsyncMock, patch

from src.voice.tts import (
    Pyttsx3Provider, EdgeTTSProvider, FallbackTTSProvider, TTSProvider, DEFAULT_VOICE, _to_percent_string,
)


class TestToPercentString:
    def test_normal_speed_is_zero_percent(self):
        assert _to_percent_string(1.0) == "+0%"

    def test_faster_than_normal_is_positive(self):
        assert _to_percent_string(1.1) == "+10%"

    def test_slower_than_normal_is_negative(self):
        assert _to_percent_string(0.9) == "-10%"


class TestDefaultVoice:
    def test_default_voice_is_male(self):
        """Regression test: the default used to be a female voice; Silva (the
        cat wizard, 'ele') needs a masculine voice by default."""
        assert "Antonio" in DEFAULT_VOICE


class TestPyttsx3Provider:
    @patch("pyttsx3.init")
    def test_speak_calls_engine(self, mock_init):
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        provider = Pyttsx3Provider()
        result = provider.speak("olá")

        mock_engine.say.assert_called_once_with("olá")
        mock_engine.runAndWait.assert_called_once()
        assert result is True

    @patch("pyttsx3.init", side_effect=RuntimeError("no engine"))
    def test_init_failure_disables_engine_without_crashing(self, mock_init):
        provider = Pyttsx3Provider()
        assert provider.engine is None
        assert provider.speak("olá") is False

    @patch("pyttsx3.init")
    def test_speak_error_does_not_propagate(self, mock_init):
        mock_engine = MagicMock()
        mock_engine.say.side_effect = RuntimeError("boom")
        mock_init.return_value = mock_engine

        provider = Pyttsx3Provider()
        assert provider.speak("olá") is False  # should not raise

    @patch("pyttsx3.init")
    def test_speak_applies_volume_and_rate(self, mock_init):
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        provider = Pyttsx3Provider()
        provider.speak("olá", volume=0.8, speed=1.2)

        mock_engine.setProperty.assert_any_call("volume", 0.8)
        mock_engine.setProperty.assert_any_call("rate", 240)  # 200 * 1.2

    @patch("pyttsx3.init")
    def test_selects_a_voice_flagged_male(self, mock_init):
        female_voice = MagicMock(id="voice-1", name="Maria", gender="VoiceGenderFemale")
        male_voice = MagicMock(id="voice-2", name="Daniel", gender="VoiceGenderMale")
        mock_engine = MagicMock()
        mock_engine.getProperty.return_value = [female_voice, male_voice]
        mock_init.return_value = mock_engine

        Pyttsx3Provider()

        mock_engine.setProperty.assert_any_call("voice", "voice-2")

    @patch("pyttsx3.init")
    def test_does_not_mistake_female_for_male(self, mock_init):
        """Regression test: 'male' is a substring of 'female', so a naive
        'male' in gender.lower() check would incorrectly match female voices."""
        only_female = MagicMock(id="voice-1", name="Maria", gender="VoiceGenderFemale")
        mock_engine = MagicMock()
        mock_engine.getProperty.return_value = [only_female]
        mock_init.return_value = mock_engine

        Pyttsx3Provider()

        for call in mock_engine.setProperty.call_args_list:
            assert call.args != ("voice", "voice-1")

    @patch("pyttsx3.init")
    def test_selection_failure_does_not_crash_init(self, mock_init):
        mock_engine = MagicMock()
        mock_engine.getProperty.side_effect = RuntimeError("no voices")
        mock_init.return_value = mock_engine

        provider = Pyttsx3Provider()

        assert provider.engine is mock_engine


class TestEdgeTTSProvider:
    def test_speak_handles_missing_edge_tts_gracefully(self):
        provider = EdgeTTSProvider()
        with patch.dict("sys.modules", {"edge_tts": None}):
            assert provider.speak("olá") is False

    def test_forwards_voice_rate_volume_pitch_to_communicate(self):
        """Regression test: speak() used to accept voice/volume/speed/pitch but
        silently ignore all of them — edge_tts.Communicate() was always called
        with just (text, voice), so no setting ever actually changed the voice."""
        fake_communicate_instance = MagicMock()
        fake_communicate_instance.save = AsyncMock()
        fake_communicate_cls = MagicMock(return_value=fake_communicate_instance)

        fake_edge_tts_module = MagicMock()
        fake_edge_tts_module.Communicate = fake_communicate_cls

        fake_pygame_module = MagicMock()
        fake_pygame_module.mixer.music.get_busy.return_value = False

        with patch.dict("sys.modules", {"edge_tts": fake_edge_tts_module, "pygame": fake_pygame_module}):
            provider = EdgeTTSProvider()
            result = provider.speak("oi", voice="pt-BR-AntonioNeural", volume=1.0, speed=1.1, pitch="+20Hz")

        fake_communicate_cls.assert_called_once_with(
            "oi", "pt-BR-AntonioNeural", rate="+10%", volume="+0%", pitch="+20Hz"
        )
        assert result is True


class TestFallbackTTSProvider:
    def test_returns_true_and_skips_fallback_when_primary_succeeds(self):
        primary = MagicMock(spec=TTSProvider)
        primary.speak.return_value = True
        fallback = MagicMock(spec=TTSProvider)

        provider = FallbackTTSProvider(primary, fallback)
        result = provider.speak("olá")

        assert result is True
        fallback.speak.assert_not_called()

    def test_falls_back_when_primary_fails(self):
        """The actual auto-recovery: EdgeTTS needing network is the realistic
        failure this guards against — primary.speak() returning False (its
        exceptions are already swallowed internally, see EdgeTTSProvider)
        must not mean total silence when a local fallback exists."""
        primary = MagicMock(spec=TTSProvider)
        primary.speak.return_value = False
        fallback = MagicMock(spec=TTSProvider)
        fallback.speak.return_value = True

        provider = FallbackTTSProvider(primary, fallback)
        result = provider.speak("olá", voice="v", volume=0.5, speed=1.2, pitch="+10Hz")

        assert result is True
        fallback.speak.assert_called_once_with("olá", voice="v", volume=0.5, speed=1.2, pitch="+10Hz")

    def test_returns_false_when_both_fail(self):
        primary = MagicMock(spec=TTSProvider)
        primary.speak.return_value = False
        fallback = MagicMock(spec=TTSProvider)
        fallback.speak.return_value = False

        provider = FallbackTTSProvider(primary, fallback)

        assert provider.speak("olá") is False

    def test_real_providers_wired_together_end_to_end(self):
        """No mocks on the fallback side: EdgeTTS genuinely unavailable
        (module missing) must still result in pyttsx3 actually being asked to
        speak, not just a well-typed mock interaction."""
        with patch("pyttsx3.init") as mock_init:
            mock_engine = MagicMock()
            mock_init.return_value = mock_engine
            provider = FallbackTTSProvider(EdgeTTSProvider(), Pyttsx3Provider())

            with patch.dict("sys.modules", {"edge_tts": None}):
                result = provider.speak("olá")

        assert result is True
        mock_engine.say.assert_called_once_with("olá")


class TestStopBargeIn:
    """FASE 14 — interrupting Silva mid-sentence."""

    def test_base_provider_stop_is_a_harmless_no_op(self):
        TTSProvider().stop()  # should not raise

    def test_edge_tts_stop_calls_pygame_mixer_stop(self):
        fake_pygame = MagicMock()
        provider = EdgeTTSProvider()
        with patch.dict("sys.modules", {"pygame": fake_pygame}):
            provider.stop()
        fake_pygame.mixer.music.stop.assert_called_once()

    def test_edge_tts_stop_with_nothing_playing_does_not_raise(self):
        provider = EdgeTTSProvider()
        with patch.dict("sys.modules", {"pygame": None}):
            provider.stop()  # should not raise

    @patch("pyttsx3.init")
    def test_pyttsx3_stop_calls_engine_stop(self, mock_init):
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine
        provider = Pyttsx3Provider()

        provider.stop()

        mock_engine.stop.assert_called_once()

    @patch("pyttsx3.init", side_effect=RuntimeError("no engine"))
    def test_pyttsx3_stop_without_an_engine_does_not_raise(self, mock_init):
        provider = Pyttsx3Provider()
        provider.stop()  # should not raise

    @patch("pyttsx3.init")
    def test_pyttsx3_stop_exception_is_caught(self, mock_init):
        mock_engine = MagicMock()
        mock_engine.stop.side_effect = RuntimeError("boom")
        mock_init.return_value = mock_engine
        provider = Pyttsx3Provider()

        provider.stop()  # should not raise

    def test_fallback_stop_calls_both_providers(self):
        primary = MagicMock(spec=TTSProvider)
        fallback = MagicMock(spec=TTSProvider)
        provider = FallbackTTSProvider(primary, fallback)

        provider.stop()

        primary.stop.assert_called_once()
        fallback.stop.assert_called_once()
