from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import Settings
from src.core.activity_log import ActivityLog
from src.core.event_bus import EventBus
from src.desktop.permission_policy import PermissionPolicyManager, PolicyDecision
from src.desktop.permissions import PermissionManager
from src.ui.settings_window import SettingsWindow


def _settings(tmp_path, **overrides):
    settings = Settings(config_path=str(tmp_path / "config.json"))
    for key, value in overrides.items():
        settings.set(key, value)
    return settings


@pytest.fixture(autouse=True)
def _mock_autostart():
    """SettingsWindow.__init__ calls autostart.is_enabled() (a real
    schtasks/registry query) and _save() calls autostart.set_enabled() (a
    real schtasks/registry WRITE — creates/deletes an actual Windows
    Scheduled Task). Every test in this file constructs a SettingsWindow,
    and several call _save() — without this, running this file repeatedly
    mutates the real machine's autostart registration as a side effect of
    unit testing, and the resulting subprocess spam is also what triggered
    a real `Fatal Python error: Aborted` crash partway through a full-suite
    run once this file's test count grew large enough. None of these tests
    are actually about autostart behavior — that's covered in
    tests/test_autostart.py."""
    with patch("src.ui.settings_window.autostart.is_enabled", return_value=False), \
         patch("src.ui.settings_window.autostart.set_enabled", return_value=True):
        yield


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

    def test_removing_an_app_revokes_its_saved_policy(self, tmp_path):
        """Regression test: an ALWAYS-approved open_application policy used to
        outlive the app's removal from the allowlist — re-adding (or
        auto-resolving) the same app name later would silently skip the
        confirmation dialog again, re-granting access nothing re-approved."""
        settings = _settings(tmp_path, allowlist={"chrome": "chrome.exe"})
        policy_manager = PermissionPolicyManager(settings)
        policy_manager.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)
        policy_manager.set_policy("close_application", "chrome", PolicyDecision.BLOCKED)
        window = SettingsWindow(settings, policy_manager=policy_manager)

        window.app_list.setCurrentRow(0)
        window._remove_selected_app()

        assert policy_manager.get_policy("open_application", "chrome") is None
        assert policy_manager.get_policy("close_application", "chrome") is None

    def test_removing_an_app_without_a_policy_manager_does_not_raise(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"chrome": "chrome.exe"})
        window = SettingsWindow(settings, policy_manager=None)

        window.app_list.setCurrentRow(0)
        window._remove_selected_app()  # should not raise

        assert window.allowlist == {}


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


class TestDiagnosticsTab:
    def test_run_diagnostics_populates_the_output_box(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings)

        window._run_diagnostics()

        text = window.diagnostics_output.toPlainText()
        assert "SILVA DIAGNOSTICS" in text
        assert "Python" in text

    def test_export_writes_the_report_to_the_chosen_file(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings)
        window._run_diagnostics()
        out_file = tmp_path / "report.txt"

        with patch("src.ui.settings_window.QFileDialog.getSaveFileName", return_value=(str(out_file), "")):
            window._export_diagnostics()

        assert out_file.exists()
        assert "SILVA DIAGNOSTICS" in out_file.read_text(encoding="utf-8")

    def test_export_cancelled_dialog_does_not_write_anything(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings)
        window._run_diagnostics()

        with patch("src.ui.settings_window.QFileDialog.getSaveFileName", return_value=("", "")):
            window._export_diagnostics()  # should not raise, nothing to assert on disk

    def test_export_without_running_first_runs_diagnostics_automatically(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings)  # diagnostics never run yet
        out_file = tmp_path / "report.txt"

        with patch("src.ui.settings_window.QFileDialog.getSaveFileName", return_value=(str(out_file), "")):
            window._export_diagnostics()

        assert "SILVA DIAGNOSTICS" in out_file.read_text(encoding="utf-8")


class TestAgentTab:
    def test_master_switches_default_off(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        assert window.input_control_chk.isChecked() is False
        assert window.terminal_tool_chk.isChecked() is False
        assert window.browser_control_chk.isChecked() is False

    def test_master_switches_reflect_saved_settings(self, tmp_path):
        settings = _settings(
            tmp_path, allowlist={}, input_control_enabled=True, terminal_tool_enabled=True,
            browser_control_enabled=True,
        )
        window = SettingsWindow(settings)
        assert window.input_control_chk.isChecked() is True
        assert window.terminal_tool_chk.isChecked() is True
        assert window.browser_control_chk.isChecked() is True

    def test_save_persists_master_switches(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        window.input_control_chk.setChecked(True)
        window.terminal_tool_chk.setChecked(True)
        window.browser_control_chk.setChecked(True)

        window._save()

        assert settings.get("input_control_enabled") is True
        assert settings.get("terminal_tool_enabled") is True
        assert settings.get("browser_control_enabled") is True

    def test_add_and_remove_terminal_tool(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        window.terminal_name_input.setText("Nmap")
        window.terminal_path_input.setText(r"C:\Program Files\Nmap\nmap.exe")

        window._add_terminal_tool()

        assert window.terminal_allowlist == {"nmap": r"C:\Program Files\Nmap\nmap.exe"}
        assert window.terminal_list.count() == 1

        window.terminal_list.setCurrentRow(0)
        window._remove_terminal_tool()
        assert window.terminal_allowlist == {}

    @patch("src.ui.settings_window.QMessageBox.warning")
    def test_add_terminal_tool_with_missing_path_is_rejected(self, mock_warning, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        window.terminal_name_input.setText("nmap")
        window.terminal_path_input.setText("")

        window._add_terminal_tool()

        assert window.terminal_allowlist == {}
        mock_warning.assert_called_once()

    def test_save_persists_terminal_allowlist(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        window.terminal_name_input.setText("nmap")
        window.terminal_path_input.setText("nmap.exe")
        window._add_terminal_tool()

        window._save()

        assert settings.get("terminal_allowlist") == {"nmap": "nmap.exe"}

    def test_save_updates_live_terminal_tool_manager_without_restart(self, tmp_path):
        from src.core.event_bus import EventBus
        from src.desktop.terminal_tool import TerminalToolManager
        settings = _settings(tmp_path, allowlist={})
        terminal_tool_manager = TerminalToolManager({"old": "old.exe"}, EventBus())
        window = SettingsWindow(settings, terminal_tool_manager=terminal_tool_manager)
        window.terminal_name_input.setText("nmap")
        window.terminal_path_input.setText("nmap.exe")
        window._add_terminal_tool()

        window._save()

        assert terminal_tool_manager.allowlist == {"nmap": "nmap.exe"}

    def test_save_without_terminal_tool_manager_does_not_raise(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings, terminal_tool_manager=None)
        window._save()  # should not raise


def _snapshot(**overrides):
    base = {
        "desktop": {"active_window": None, "category": None, "is_game": False, "idle_seconds": 0},
        "vision": {"monitoring_enabled": False, "private_mode": True},
        "voice": {"listening": False, "hands_free_enabled": False, "system_audio_listening": False},
        "memory": {"saved_keys": [], "saved_count": 0},
    }
    base.update(overrides)
    return base


class TestSilvaModeSelector:
    def test_combo_lists_every_mode_capitalized(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        labels = {window.mode_combo.itemText(i) for i in range(window.mode_combo.count())}
        assert labels == {"Silencioso", "Trabalho", "Companhia", "Foco", "Privacidade", "Jogo"}

    def test_apply_calls_the_injected_function_with_the_lowercase_mode_name(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        apply_fn = MagicMock()
        window = SettingsWindow(settings, apply_silva_mode_fn=apply_fn)
        window.mode_combo.setCurrentText("Jogo")

        with patch("src.ui.settings_window.QMessageBox.information"):
            window._apply_selected_mode()

        apply_fn.assert_called_once_with("jogo")

    def test_apply_without_a_function_does_not_raise(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings, apply_silva_mode_fn=None)
        window.mode_combo.setCurrentText("Foco")

        with patch("src.ui.settings_window.QMessageBox.information"):
            window._apply_selected_mode()  # should not raise

    def test_tooltip_updates_when_selection_changes(self, tmp_path):
        from src.core.silva_modes import MODE_DESCRIPTIONS
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings)
        window.mode_combo.setCurrentText("Jogo")
        assert window.mode_combo.toolTip() == MODE_DESCRIPTIONS["jogo"]


class TestPrivacyTab:
    def test_without_silva_state_shows_a_fallback_message(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        window = SettingsWindow(settings, silva_state=None)
        assert "indisponível" in window.privacy_output.toPlainText()

    def test_shows_the_formatted_summary(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        silva_state = MagicMock()
        silva_state.snapshot.return_value = _snapshot(
            memory={"saved_keys": ["cor favorita"], "saved_count": 1}
        )
        window = SettingsWindow(settings, silva_state=silva_state)

        text = window.privacy_output.toPlainText()

        assert "O QUE A SILVA VÊ" in text
        assert "cor favorita" in text

    def test_memory_list_is_populated_from_the_snapshot(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        silva_state = MagicMock()
        silva_state.snapshot.return_value = _snapshot(
            memory={"saved_keys": ["cor favorita", "cidade natal"], "saved_count": 2}
        )
        window = SettingsWindow(settings, silva_state=silva_state)

        assert window.memory_list.count() == 2

    def test_forget_selected_memory_calls_memory_manager(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        silva_state = MagicMock()
        silva_state.snapshot.return_value = _snapshot(
            memory={"saved_keys": ["cor favorita"], "saved_count": 1}
        )
        memory_manager = MagicMock()
        window = SettingsWindow(settings, silva_state=silva_state, memory_manager=memory_manager)
        window.memory_list.setCurrentRow(0)

        window._forget_selected_memory()

        memory_manager.forget.assert_called_once_with("cor favorita")

    def test_forget_without_selection_does_not_raise(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        silva_state = MagicMock()
        silva_state.snapshot.return_value = _snapshot()
        memory_manager = MagicMock()
        window = SettingsWindow(settings, silva_state=silva_state, memory_manager=memory_manager)

        window._forget_selected_memory()  # should not raise

        memory_manager.forget.assert_not_called()

    def test_forget_without_memory_manager_does_not_raise(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        silva_state = MagicMock()
        silva_state.snapshot.return_value = _snapshot(
            memory={"saved_keys": ["cor favorita"], "saved_count": 1}
        )
        window = SettingsWindow(settings, silva_state=silva_state, memory_manager=None)
        window.memory_list.setCurrentRow(0)

        window._forget_selected_memory()  # should not raise

    def test_refresh_button_pulls_a_fresh_snapshot(self, tmp_path):
        settings = _settings(tmp_path, allowlist={})
        silva_state = MagicMock()
        silva_state.snapshot.return_value = _snapshot()
        window = SettingsWindow(settings, silva_state=silva_state)
        assert silva_state.snapshot.call_count == 1

        window._refresh_privacy_summary()

        assert silva_state.snapshot.call_count == 2


class TestActivityTab:
    def test_without_an_activity_log_shows_the_empty_message(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        window = SettingsWindow(settings, activity_log=None)

        text = window.activity_output.toPlainText()

        assert "Nenhuma atividade registrada ainda." in text

    def test_shows_entries_from_the_provided_activity_log(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        bus = EventBus()
        bus.reset()
        activity_log = ActivityLog(bus)
        bus.emit("MEMORY_CREATED", key="comida favorita", value="pizza")
        window = SettingsWindow(settings, activity_log=activity_log)

        text = window.activity_output.toPlainText()

        assert "comida favorita" in text

    def test_refresh_button_pulls_in_new_entries(self, tmp_path):
        settings = _settings(tmp_path, allowlist={"notepad": "notepad.exe"})
        bus = EventBus()
        bus.reset()
        activity_log = ActivityLog(bus)
        window = SettingsWindow(settings, activity_log=activity_log)
        assert "cor favorita" not in window.activity_output.toPlainText()

        bus.emit("MEMORY_CREATED", key="cor favorita", value="azul")
        window._refresh_activity_log()

        assert "cor favorita" in window.activity_output.toPlainText()
