from unittest.mock import patch

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
    the real Windows registry."""
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

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


class TestIsEnabled:
    def test_false_when_no_value_set(self):
        with patch.object(autostart, "winreg", FakeWinreg()):
            assert autostart.is_enabled() is False

    def test_true_after_enabling(self):
        with patch.object(autostart, "winreg", FakeWinreg()):
            autostart.set_enabled(True)
            assert autostart.is_enabled() is True

    def test_false_when_winreg_unavailable(self):
        with patch.object(autostart, "winreg", None):
            assert autostart.is_enabled() is False

    def test_false_on_registry_error(self):
        fake = FakeWinreg()
        fake.QueryValueEx = lambda key, name: (_ for _ in ()).throw(OSError("boom"))
        with patch.object(autostart, "winreg", fake):
            assert autostart.is_enabled() is False


class TestSetEnabled:
    def test_enabling_writes_launch_command(self):
        fake = FakeWinreg()
        with patch.object(autostart, "winreg", fake):
            result = autostart.set_enabled(True)

        assert result is True
        assert autostart.REGISTRY_VALUE_NAME in fake.values
        assert "main.py" in fake.values[autostart.REGISTRY_VALUE_NAME]

    def test_disabling_removes_value(self):
        fake = FakeWinreg()
        with patch.object(autostart, "winreg", fake):
            autostart.set_enabled(True)
            result = autostart.set_enabled(False)

        assert result is True
        assert autostart.REGISTRY_VALUE_NAME not in fake.values

    def test_disabling_when_already_disabled_is_a_noop(self):
        fake = FakeWinreg()
        with patch.object(autostart, "winreg", fake):
            result = autostart.set_enabled(False)

        assert result is True
        assert autostart.REGISTRY_VALUE_NAME not in fake.values

    def test_returns_false_when_winreg_unavailable(self):
        with patch.object(autostart, "winreg", None):
            assert autostart.set_enabled(True) is False

    def test_returns_false_on_registry_error(self):
        fake = FakeWinreg()
        fake.OpenKey = lambda *a: (_ for _ in ()).throw(OSError("boom"))
        with patch.object(autostart, "winreg", fake):
            assert autostart.set_enabled(True) is False


class TestLaunchCommand:
    def test_uses_pythonw_when_available(self):
        with patch("os.path.exists", return_value=True):
            cmd = autostart._launch_command()
        assert "pythonw.exe" in cmd

    def test_falls_back_to_current_interpreter_when_no_pythonw(self):
        with patch("os.path.exists", return_value=False):
            cmd = autostart._launch_command()
        assert "pythonw.exe" not in cmd
