from unittest.mock import MagicMock, patch

from src.voice.tts import Pyttsx3Provider, EdgeTTSProvider


class TestPyttsx3Provider:
    @patch("pyttsx3.init")
    def test_speak_calls_engine(self, mock_init):
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        provider = Pyttsx3Provider()
        provider.speak("olá")

        mock_engine.say.assert_called_once_with("olá")
        mock_engine.runAndWait.assert_called_once()

    @patch("pyttsx3.init", side_effect=RuntimeError("no engine"))
    def test_init_failure_disables_engine_without_crashing(self, mock_init):
        provider = Pyttsx3Provider()
        assert provider.engine is None
        provider.speak("olá")

    @patch("pyttsx3.init")
    def test_speak_error_does_not_propagate(self, mock_init):
        mock_engine = MagicMock()
        mock_engine.say.side_effect = RuntimeError("boom")
        mock_init.return_value = mock_engine

        provider = Pyttsx3Provider()
        provider.speak("olá")  # should not raise


class TestEdgeTTSProvider:
    def test_speak_handles_missing_edge_tts_gracefully(self):
        provider = EdgeTTSProvider()
        with patch.dict("sys.modules", {"edge_tts": None}):
            provider.speak("olá")
