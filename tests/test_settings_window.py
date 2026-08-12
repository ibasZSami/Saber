from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.desktop.permissions import PermissionManager
from src.ui.settings_window import SettingsWindow


def _settings(tmp_path, **overrides):
    settings = Settings(config_path=str(tmp_path / "config.json"))
    for key, value in overrides.items():
        settings.set(key, value)
    return settings


class TestAppAllowlistTab:
    def test_starts_with_allowlist_from_settings(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings)
        assert window.allowlist == {"notepad": "notepad.exe"}
        assert window.app_list.count() == 1

    def test_add_app_to_allowlist(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        window.app_name_input.setText("Firefox")
        window.app_path_input.setText(r"C:\Program Files\Mozilla Firefox\firefox.exe")

        window._add_app_to_allowlist()

        assert window.allowlist == {"firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe"}
        assert window.app_list.count() == 1
        assert window.app_name_input.text() == ""
        assert window.app_path_input.text() == ""

    @patch("src.ui.settings_window.QMessageBox.warning")
    def test_add_app_with_missing_path_is_rejected(self, mock_warning, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        window.app_name_input.setText("firefox")
        window.app_path_input.setText("")

        window._add_app_to_allowlist()

        assert window.allowlist == {}
        mock_warning.assert_called_once()

    def test_remove_selected_app(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe", "chrome": "chrome.exe"})
        window = SettingsWindow(settings)

        window.app_list.setCurrentRow(0)
        window._remove_selected_app()

        assert len(window.allowlist) == 1

    def test_remove_with_nothing_selected_does_not_raise(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings)
        window.app_list.clearSelection()
        window.app_list.setCurrentItem(None)

        window._remove_selected_app()  # should not raise

        assert window.allowlist == {"notepad": "notepad.exe"}


class TestSaveSyncsAllowlist:
    def test_save_persists_allowlist_into_settings(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings)
        window.app_name_input.setText("firefox")
        window.app_path_input.setText("firefox.exe")
        window._add_app_to_allowlist()

        window._save()

        assert settings.get("allowlist") == {"notepad": "notepad.exe", "firefox": "firefox.exe"}

    def test_save_updates_live_permission_manager_without_restart(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        permission_manager = PermissionManager({"notepad": "notepad.exe"})
        window = SettingsWindow(settings, permission_manager)
        window.app_name_input.setText("firefox")
        window.app_path_input.setText("firefox.exe")
        window._add_app_to_allowlist()

        window._save()

        assert permission_manager.is_app_allowed("firefox")
        assert permission_manager.get_app_command("firefox") == "firefox.exe"

    def test_save_without_permission_manager_does_not_raise(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings, permission_manager=None)

        window._save()  # should not raise
