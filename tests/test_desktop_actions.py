from unittest.mock import MagicMock, patch

import psutil

from src.desktop.actions import DesktopActionManager
from src.desktop.permissions import PermissionManager


def _fake_process(name):
    proc = MagicMock()
    proc.info = {"name": name}
    return proc


class TestOpenApplication:
    @patch("subprocess.Popen")
    def test_not_allowed_returns_false_without_launching(self, mock_popen):
        pm = PermissionManager({"notepad": "notepad.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.open_application("chrome")

        assert result is False
        mock_popen.assert_not_called()

    @patch("subprocess.Popen")
    def test_quotes_exe_path_with_spaces(self, mock_popen):
        pm = PermissionManager({"chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe"})
        mgr = DesktopActionManager(pm)

        mgr.open_application("chrome")

        called_cmd = mock_popen.call_args[0][0]
        assert called_cmd == r'"C:\Program Files\Google\Chrome\Application\chrome.exe"'

    @patch("subprocess.Popen")
    def test_quotes_exe_path_and_keeps_trailing_args(self, mock_popen):
        pm = PermissionManager({"discord": r"C:\Users\ribas\AppData\Local\Discord\Update.exe --processStart Discord.exe"})
        mgr = DesktopActionManager(pm)

        mgr.open_application("discord")

        called_cmd = mock_popen.call_args[0][0]
        assert called_cmd == r'"C:\Users\ribas\AppData\Local\Discord\Update.exe" --processStart Discord.exe'

    @patch("subprocess.Popen")
    def test_no_quoting_needed_for_simple_command(self, mock_popen):
        pm = PermissionManager({"vscode": "code"})
        mgr = DesktopActionManager(pm)

        mgr.open_application("vscode")

        assert mock_popen.call_args[0][0] == "code"

    @patch("subprocess.Popen", side_effect=OSError("boom"))
    def test_launch_failure_returns_false(self, mock_popen):
        pm = PermissionManager({"vscode": "code"})
        mgr = DesktopActionManager(pm)

        assert mgr.open_application("vscode") is False

    @patch("subprocess.Popen")
    def test_is_case_insensitive(self, mock_popen):
        pm = PermissionManager({"chrome": "chrome.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.open_application("  Chrome  ")

        assert result is True
        mock_popen.assert_called_once()


class TestCloseApplication:
    @patch("src.desktop.actions.psutil.process_iter")
    def test_not_allowed_returns_false_without_terminating_anything(self, mock_iter):
        pm = PermissionManager({"notepad": "notepad.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.close_application("chrome")

        assert result is False
        mock_iter.assert_not_called()

    @patch("src.desktop.actions.psutil.process_iter")
    def test_terminates_matching_process_exact_name(self, mock_iter):
        proc = _fake_process("notepad.exe")
        mock_iter.return_value = [proc]
        pm = PermissionManager({"notepad": "notepad.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.close_application("notepad")

        assert result is True
        proc.terminate.assert_called_once()

    @patch("src.desktop.actions.psutil.process_iter")
    def test_matches_process_via_substring_either_direction(self, mock_iter):
        """The allowlist key ('vscode') and the real running process name
        ('Code.exe') don't match exactly — this covers that mismatch."""
        proc = _fake_process("Code.exe")
        mock_iter.return_value = [proc]
        pm = PermissionManager({"vscode": "code"})
        mgr = DesktopActionManager(pm)

        result = mgr.close_application("vscode")

        assert result is True
        proc.terminate.assert_called_once()

    @patch("src.desktop.actions.psutil.process_iter")
    def test_no_matching_process_returns_false(self, mock_iter):
        proc = _fake_process("firefox.exe")
        mock_iter.return_value = [proc]
        pm = PermissionManager({"chrome": "chrome.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.close_application("chrome")

        assert result is False
        proc.terminate.assert_not_called()

    @patch("src.desktop.actions.psutil.process_iter")
    def test_closes_all_matching_processes(self, mock_iter):
        proc1 = _fake_process("chrome.exe")
        proc2 = _fake_process("chrome.exe")
        mock_iter.return_value = [proc1, proc2]
        pm = PermissionManager({"chrome": "chrome.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.close_application("chrome")

        assert result is True
        proc1.terminate.assert_called_once()
        proc2.terminate.assert_called_once()

    @patch("src.desktop.actions.psutil.process_iter")
    def test_skips_process_that_disappears_mid_iteration(self, mock_iter):
        class _GoneProcess:
            info = {"name": "chrome.exe"}

            def terminate(self):
                raise psutil.NoSuchProcess(1234)

        mock_iter.return_value = [_GoneProcess()]
        pm = PermissionManager({"chrome": "chrome.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.close_application("chrome")

        assert result is False

    @patch("src.desktop.actions.psutil.process_iter")
    def test_is_case_insensitive(self, mock_iter):
        proc = _fake_process("Chrome.exe")
        mock_iter.return_value = [proc]
        pm = PermissionManager({"chrome": "chrome.exe"})
        mgr = DesktopActionManager(pm)

        result = mgr.close_application("  CHROME  ")

        assert result is True
        proc.terminate.assert_called_once()


class TestSearchWeb:
    @patch("webbrowser.open")
    def test_url_encodes_special_characters(self, mock_open):
        mgr = DesktopActionManager(PermissionManager({}))

        mgr.search_web("C++ & Python tutorial?")

        called_url = mock_open.call_args[0][0]
        assert called_url.startswith("https://www.google.com/search?q=")
        assert " " not in called_url
        assert "%26" in called_url  # '&' safely encoded, doesn't break the query string

    @patch("webbrowser.open")
    def test_plain_query_roundtrips(self, mock_open):
        mgr = DesktopActionManager(PermissionManager({}))

        mgr.search_web("python tutorial")

        called_url = mock_open.call_args[0][0]
        assert called_url == "https://www.google.com/search?q=python+tutorial"


class TestOpenUrl:
    @patch("webbrowser.open")
    def test_adds_https_scheme_when_missing(self, mock_open):
        mgr = DesktopActionManager(PermissionManager({}))
        mgr.open_url("example.com")
        mock_open.assert_called_once_with("https://example.com")

    @patch("webbrowser.open")
    def test_keeps_existing_scheme(self, mock_open):
        mgr = DesktopActionManager(PermissionManager({}))
        mgr.open_url("http://example.com")
        mock_open.assert_called_once_with("http://example.com")

    @patch("webbrowser.open", side_effect=RuntimeError("boom"))
    def test_failure_returns_false(self, mock_open):
        mgr = DesktopActionManager(PermissionManager({}))
        assert mgr.open_url("example.com") is False
