from unittest.mock import MagicMock, patch

import src.core.autostart as autostart


class _FakeKey:
    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWinreg:
    """Minimal in-memory stand-in for the winreg module, so tests never touch
    the real Windows registry — only used here for the legacy Run-key cleanup
    path, since autostart itself now lives in the Scheduled Task."""
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self, values=None):
        self.values = values or {}

    def OpenKey(self, hive, path, reserved, access):
        return _FakeKey(self)

    def QueryValueEx(self, key, name):
        if name not in key.registry.values:
            raise FileNotFoundError()
        return (key.registry.values[name], 1)

    def SetValueEx(self, key, name, reserved, value_type, data):
        key.registry.values[name] = data

    def DeleteValue(self, key, name):
        if name not in key.registry.values:
            raise FileNotFoundError()
        del key.registry.values[name]


def _completed(returncode=0, stderr=b""):
    result = MagicMock()
    result.returncode = returncode
    result.stderr = stderr
    return result


class TestIsEnabled:
    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run")
    def test_true_when_task_query_succeeds(self, mock_run):
        mock_run.return_value = _completed(returncode=0)
        assert autostart.is_enabled() is True
        args = mock_run.call_args[0][0]
        assert args[:3] == ["schtasks", "/query", "/tn"]
        assert autostart.TASK_NAME in args

    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run")
    def test_false_when_task_does_not_exist(self, mock_run):
        mock_run.return_value = _completed(returncode=1)
        assert autostart.is_enabled() is False

    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run", side_effect=OSError("schtasks not found"))
    def test_false_when_schtasks_unavailable(self, mock_run):
        assert autostart.is_enabled() is False

    @patch("subprocess.run")
    def test_true_when_task_missing_but_legacy_run_key_present(self, mock_run):
        """Fallback signal: if the Scheduled Task couldn't be created on this
        machine (see TestFallsBackToRunKey) but the legacy Run-key is set,
        Silva is still genuinely registered to auto-launch — just via the
        older mechanism."""
        mock_run.return_value = _completed(returncode=1)
        fake = FakeWinreg({autostart.REGISTRY_VALUE_NAME: "some command"})
        with patch.object(autostart, "winreg", fake):
            assert autostart.is_enabled() is True

    @patch("subprocess.run")
    def test_false_when_neither_mechanism_is_registered(self, mock_run):
        mock_run.return_value = _completed(returncode=1)
        fake = FakeWinreg({})
        with patch.object(autostart, "winreg", fake):
            assert autostart.is_enabled() is False


class TestSetEnabledCreatesTask:
    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run")
    def test_enabling_creates_task_via_xml(self, mock_run):
        mock_run.return_value = _completed(returncode=0)

        result = autostart.set_enabled(True)

        assert result is True
        args = mock_run.call_args[0][0]
        assert args[0] == "schtasks"
        assert "/create" in args
        assert "/tn" in args
        assert autostart.TASK_NAME in args
        assert "/xml" in args

    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run")
    def test_enabling_returns_false_on_failure(self, mock_run):
        mock_run.return_value = _completed(returncode=1, stderr=b"Access denied")

        assert autostart.set_enabled(True) is False

    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run", side_effect=OSError("boom"))
    def test_enabling_returns_false_when_schtasks_unavailable(self, mock_run):
        assert autostart.set_enabled(True) is False

    @patch.object(autostart, "winreg", None)
    @patch("os.unlink")
    @patch("subprocess.run")
    def test_temp_xml_file_is_cleaned_up(self, mock_run, mock_unlink):
        mock_run.return_value = _completed(returncode=0)

        autostart.set_enabled(True)

        mock_unlink.assert_called_once()


class TestSetEnabledRemovesTask:
    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run")
    def test_disabling_deletes_task(self, mock_run):
        mock_run.return_value = _completed(returncode=0)

        result = autostart.set_enabled(False)

        assert result is True
        args = mock_run.call_args[0][0]
        assert args[0] == "schtasks"
        assert "/delete" in args
        assert autostart.TASK_NAME in args

    @patch.object(autostart, "winreg", None)
    @patch("subprocess.run")
    def test_disabling_when_already_disabled_is_a_noop(self, mock_run):
        # /delete fails (nothing to delete), then the is_enabled() recheck
        # also reports "not there" — treated as success, not a real failure.
        mock_run.side_effect = [_completed(returncode=1), _completed(returncode=1)]

        assert autostart.set_enabled(False) is True


class TestFallsBackToRunKey:
    """Some machines deny `schtasks /create` to the current account even for a
    per-user task (seen in the field as a bare "Acesso negado") — autostart
    should still end up working via the legacy Run-key instead of just
    logging an error and leaving the user with nothing registered."""

    @patch("subprocess.run")
    def test_enabling_falls_back_when_task_creation_is_denied(self, mock_run):
        mock_run.return_value = _completed(returncode=1, stderr=b"Acesso negado")
        fake = FakeWinreg({})
        with patch.object(autostart, "winreg", fake):
            result = autostart.set_enabled(True)

        assert result is True
        assert fake.values[autostart.REGISTRY_VALUE_NAME] == autostart._launch_command()

    @patch("subprocess.run")
    def test_returns_false_when_both_mechanisms_fail(self, mock_run):
        mock_run.return_value = _completed(returncode=1, stderr=b"Acesso negado")
        with patch.object(autostart, "winreg", None):
            assert autostart.set_enabled(True) is False

    @patch("subprocess.run")
    def test_successful_task_creation_cleans_up_any_fallback_entry(self, mock_run):
        """Once the Scheduled Task works (e.g. after a machine's policy
        changes), any Run-key left over from an earlier fallback must be
        removed — otherwise Silva would launch twice on every logon."""
        mock_run.return_value = _completed(returncode=0)
        fake = FakeWinreg({autostart.REGISTRY_VALUE_NAME: "old fallback command"})
        with patch.object(autostart, "winreg", fake):
            result = autostart.set_enabled(True)

        assert result is True
        assert autostart.REGISTRY_VALUE_NAME not in fake.values


class TestLegacyRunKeyCleanup:
    def test_removes_leftover_legacy_entry_when_present(self):
        fake = FakeWinreg({autostart.REGISTRY_VALUE_NAME: "some old command"})
        with patch.object(autostart, "winreg", fake), patch("subprocess.run", return_value=_completed(0)):
            autostart.set_enabled(True)
        assert autostart.REGISTRY_VALUE_NAME not in fake.values

    def test_no_error_when_no_legacy_entry_exists(self):
        fake = FakeWinreg({})
        with patch.object(autostart, "winreg", fake), patch("subprocess.run", return_value=_completed(0)):
            result = autostart.set_enabled(True)
        assert result is True

    def test_no_error_when_winreg_unavailable(self):
        with patch.object(autostart, "winreg", None), patch("subprocess.run", return_value=_completed(0)):
            assert autostart.set_enabled(True) is True


class TestLaunchPaths:
    def test_uses_pythonw_when_available(self):
        with patch("os.path.exists", return_value=True):
            cmd = autostart._launch_command()
        assert "pythonw.exe" in cmd

    def test_falls_back_to_current_interpreter_when_no_pythonw(self):
        with patch("os.path.exists", return_value=False):
            cmd = autostart._launch_command()
        assert "pythonw.exe" not in cmd

    def test_frozen_build_launches_the_exe_directly_with_no_main_py_argument(self):
        """In a PyInstaller build there's no main.py to point a separate
        interpreter at — sys.executable IS Silva.exe. Regression guard for a
        real bug: unpatched, this used to produce '"Silva.exe" "...main.py"',
        which fails since a frozen build ships no main.py at all."""
        with patch("sys.frozen", True, create=True), \
                patch("sys.executable", r"C:\Program Files\Silva\Silva.exe"):
            interpreter, main_py = autostart._launch_paths()
            cmd = autostart._launch_command()

        assert interpreter == r"C:\Program Files\Silva\Silva.exe"
        assert main_py is None
        assert cmd == r'"C:\Program Files\Silva\Silva.exe"'
        assert "main.py" not in cmd


class TestTaskXml:
    def test_includes_logon_and_session_unlock_triggers(self):
        """The whole point of the Task Scheduler switch: cover both a fresh
        logon AND waking/unlocking an already-running session, since a
        Run-key entry only ever fires on the former."""
        xml = autostart._task_xml()
        assert "<LogonTrigger>" in xml
        assert "<SessionStateChangeTrigger>" in xml
        assert "<StateChange>SessionUnlock</StateChange>" in xml

    def test_ignores_new_instance_if_already_running(self):
        xml = autostart._task_xml()
        assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml

    def test_embeds_the_resolved_interpreter_and_main_py(self):
        with patch("os.path.exists", return_value=True):
            xml = autostart._task_xml()
        assert "pythonw.exe" in xml
        assert "main.py" in xml

    def test_frozen_build_omits_the_arguments_element(self):
        with patch("sys.frozen", True, create=True), \
                patch("sys.executable", r"C:\Program Files\Silva\Silva.exe"):
            xml = autostart._task_xml()

        assert "Silva.exe" in xml
        assert "<Arguments>" not in xml
        assert "main.py" not in xml
