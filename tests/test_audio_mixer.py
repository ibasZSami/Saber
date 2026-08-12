from unittest.mock import MagicMock, patch

from src.desktop.audio_mixer import AudioMixerManager


def _fake_session(proc_name):
    session = MagicMock()
    if proc_name is None:
        session.Process = None
    else:
        session.Process.name.return_value = proc_name
    return session


class TestSetVolume:
    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_sets_volume_on_matching_session(self, mock_audio_utilities):
        session = _fake_session("Discord.exe")
        mock_audio_utilities.GetAllSessions.return_value = [session]
        mgr = AudioMixerManager()

        result = mgr.set_volume("discord", 0.2)

        assert result is True
        session.SimpleAudioVolume.SetMasterVolume.assert_called_once_with(0.2, None)

    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_matches_process_via_substring_either_direction(self, mock_audio_utilities):
        """Same mismatch as close_application: allowlist-style key ('vscode')
        vs. the real running process ('Code.exe')."""
        session = _fake_session("Code.exe")
        mock_audio_utilities.GetAllSessions.return_value = [session]
        mgr = AudioMixerManager()

        result = mgr.set_volume("vscode", 0.5)

        assert result is True
        session.SimpleAudioVolume.SetMasterVolume.assert_called_once_with(0.5, None)

    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_no_matching_session_returns_false(self, mock_audio_utilities):
        session = _fake_session("firefox.exe")
        mock_audio_utilities.GetAllSessions.return_value = [session]
        mgr = AudioMixerManager()

        result = mgr.set_volume("chrome", 0.3)

        assert result is False
        session.SimpleAudioVolume.SetMasterVolume.assert_not_called()

    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_skips_session_with_no_process(self, mock_audio_utilities):
        no_proc_session = _fake_session(None)
        real_session = _fake_session("chrome.exe")
        mock_audio_utilities.GetAllSessions.return_value = [no_proc_session, real_session]
        mgr = AudioMixerManager()

        result = mgr.set_volume("chrome", 0.4)

        assert result is True
        real_session.SimpleAudioVolume.SetMasterVolume.assert_called_once_with(0.4, None)

    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_clamps_level_to_valid_range(self, mock_audio_utilities):
        session = _fake_session("chrome.exe")
        mock_audio_utilities.GetAllSessions.return_value = [session]
        mgr = AudioMixerManager()

        mgr.set_volume("chrome", 5.0)
        session.SimpleAudioVolume.SetMasterVolume.assert_called_once_with(1.0, None)

        session.SimpleAudioVolume.SetMasterVolume.reset_mock()
        mgr.set_volume("chrome", -3.0)
        session.SimpleAudioVolume.SetMasterVolume.assert_called_once_with(0.0, None)

    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_is_case_insensitive(self, mock_audio_utilities):
        session = _fake_session("Chrome.exe")
        mock_audio_utilities.GetAllSessions.return_value = [session]
        mgr = AudioMixerManager()

        result = mgr.set_volume("  CHROME  ", 0.5)

        assert result is True

    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_set_master_volume_exception_returns_false(self, mock_audio_utilities):
        session = _fake_session("chrome.exe")
        session.SimpleAudioVolume.SetMasterVolume.side_effect = RuntimeError("boom")
        mock_audio_utilities.GetAllSessions.return_value = [session]
        mgr = AudioMixerManager()

        assert mgr.set_volume("chrome", 0.5) is False

    @patch("src.desktop.audio_mixer.AudioUtilities")
    def test_get_all_sessions_exception_returns_false(self, mock_audio_utilities):
        mock_audio_utilities.GetAllSessions.side_effect = RuntimeError("boom")
        mgr = AudioMixerManager()

        assert mgr.set_volume("chrome", 0.5) is False

    def test_missing_pycaw_dependency_returns_false(self):
        with patch("src.desktop.audio_mixer.AudioUtilities", None):
            mgr = AudioMixerManager()
            assert mgr.set_volume("chrome", 0.5) is False
