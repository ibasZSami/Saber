from unittest.mock import MagicMock, patch

from src.desktop.application_manager import ApplicationManager
from src.desktop.window_manager import WindowManager


class TestWindowManager:
    def test_returns_fallback_when_pygetwindow_unavailable(self):
        wm = WindowManager()
        with patch("src.desktop.window_manager.gw", None):
            info = wm.get_active_window_info()
        assert info["title"] == "Desktop / Unknown"

    def test_returns_active_window_title(self):
        wm = WindowManager()
        fake_window = MagicMock(title="Notepad", width=800, height=600)
        with patch("src.desktop.window_manager.gw") as mock_gw:
            mock_gw.getActiveWindow.return_value = fake_window
            info = wm.get_active_window_info()
        assert info["title"] == "Notepad"
        assert info["width"] == 800

    def test_handles_exception_gracefully(self):
        wm = WindowManager()
        with patch("src.desktop.window_manager.gw") as mock_gw:
            mock_gw.getActiveWindow.side_effect = RuntimeError("boom")
            info = wm.get_active_window_info()
        assert info["title"] == "Desktop / Unknown"


class TestApplicationManager:
    def _mgr_with_title(self, title):
        wm = MagicMock()
        wm.get_active_window_info.return_value = {"title": title}
        return ApplicationManager(wm)

    def test_detects_game(self):
        ctx = self._mgr_with_title("Minecraft 1.20").detect_context()
        assert ctx["is_game"] is True
        assert ctx["category"] == "gaming"

    def test_detects_browser(self):
        ctx = self._mgr_with_title("YouTube - Google Chrome").detect_context()
        assert ctx["category"] == "browser"
        assert ctx["is_game"] is False

    def test_detects_coding(self):
        ctx = self._mgr_with_title("orchestrator.py - Visual Studio Code").detect_context()
        assert ctx["category"] == "coding"

    def test_detects_chat(self):
        ctx = self._mgr_with_title("General - Discord").detect_context()
        assert ctx["category"] == "chat"

    def test_defaults_to_general(self):
        ctx = self._mgr_with_title("File Explorer").detect_context()
        assert ctx["category"] == "general"
