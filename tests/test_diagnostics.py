from unittest.mock import patch

from src.core.diagnostics import CheckStatus, DiagnosticCheck, format_report, run_diagnostics


class _FakeSettings:
    def __init__(self, **overrides):
        self.config_path = "C:\\fake\\config.json"
        self.data = {
            "ai_provider": "nvidia",
            "api_key": "nvapi-secret-value",
            "assets_path": "",
            "allowlist": {"chrome": "chrome.exe"},
            "character_name": "Silva",
        }
        self.data.update(overrides)

    def get(self, key, default=None):
        return self.data.get(key, default)


class TestRunDiagnosticsShape:
    def test_returns_a_check_for_every_expected_area(self):
        checks = run_diagnostics(_FakeSettings())
        names = {c.name for c in checks}
        assert names == {
            "Python", "Qt", "Audio input", "Audio output", "Whisper", "Tesseract",
            "API", "Assets", "Configuration", "Permissions", "Autostart",
        }

    def test_a_crashing_check_becomes_a_fail_result_not_an_exception(self):
        """Regression guard: one check raising must not take the whole report
        down — it becomes a FAIL entry for just that check."""
        with patch("src.core.diagnostics._check_python", side_effect=RuntimeError("boom")):
            checks = run_diagnostics(_FakeSettings())  # must not raise

        python_check = next(c for c in checks if c.name == "Python")
        assert python_check.status == CheckStatus.FAIL
        assert "boom" in python_check.detail


class TestApiKeyCheckNeverLeaksTheSecret:
    def test_configured_key_reports_presence_not_the_value(self):
        settings = _FakeSettings(api_key="nvapi-super-secret-abc123")
        checks = run_diagnostics(settings)
        api_check = next(c for c in checks if c.name == "API")
        assert api_check.status == CheckStatus.OK
        assert "nvapi-super-secret-abc123" not in api_check.detail
        assert "nvapi-super-secret-abc123" not in format_report(checks)

    def test_missing_key_fails(self):
        settings = _FakeSettings(api_key="")
        checks = run_diagnostics(settings)
        api_check = next(c for c in checks if c.name == "API")
        assert api_check.status == CheckStatus.FAIL

    def test_ollama_needs_no_key(self):
        settings = _FakeSettings(ai_provider="ollama", api_key="")
        checks = run_diagnostics(settings)
        api_check = next(c for c in checks if c.name == "API")
        assert api_check.status == CheckStatus.OK


class TestAssetsCheck:
    def test_missing_directory_fails(self):
        settings = _FakeSettings(assets_path="C:\\does\\not\\exist")
        checks = run_diagnostics(settings)
        assets_check = next(c for c in checks if c.name == "Assets")
        assert assets_check.status == CheckStatus.FAIL

    def test_directory_with_sprites_passes(self, tmp_path):
        (tmp_path / "idle.png").write_bytes(b"\x89PNG")
        (tmp_path / "walk.png").write_bytes(b"\x89PNG")
        settings = _FakeSettings(assets_path=str(tmp_path))

        checks = run_diagnostics(settings)

        assets_check = next(c for c in checks if c.name == "Assets")
        assert assets_check.status == CheckStatus.OK
        assert "2" in assets_check.detail

    def test_directory_without_sprites_fails(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not a sprite")
        settings = _FakeSettings(assets_path=str(tmp_path))

        checks = run_diagnostics(settings)

        assets_check = next(c for c in checks if c.name == "Assets")
        assert assets_check.status == CheckStatus.FAIL


class TestPermissionsCheck:
    def test_empty_allowlist_warns(self):
        settings = _FakeSettings(allowlist={})
        checks = run_diagnostics(settings)
        perm_check = next(c for c in checks if c.name == "Permissions")
        assert perm_check.status == CheckStatus.WARN

    def test_non_empty_allowlist_passes(self):
        settings = _FakeSettings(allowlist={"chrome": "chrome.exe", "discord": "discord.exe"})
        checks = run_diagnostics(settings)
        perm_check = next(c for c in checks if c.name == "Permissions")
        assert perm_check.status == CheckStatus.OK
        assert "2" in perm_check.detail


class TestAudioChecks:
    def test_input_ok_when_an_input_device_exists(self):
        with patch("src.core.diagnostics._query_audio_devices", return_value=[{"max_input_channels": 2, "max_output_channels": 0}]):
            checks = run_diagnostics(_FakeSettings())
        assert next(c for c in checks if c.name == "Audio input").status == CheckStatus.OK
        assert next(c for c in checks if c.name == "Audio output").status == CheckStatus.WARN

    def test_query_failure_becomes_fail_not_an_exception(self):
        with patch("src.core.diagnostics._query_audio_devices", side_effect=RuntimeError("no backend")):
            checks = run_diagnostics(_FakeSettings())
        assert next(c for c in checks if c.name == "Audio input").status == CheckStatus.FAIL
        assert next(c for c in checks if c.name == "Audio output").status == CheckStatus.FAIL


class TestAutostartCheck:
    def test_reflects_autostart_is_enabled_true(self):
        with patch("src.core.autostart.is_enabled", return_value=True):
            checks = run_diagnostics(_FakeSettings())
        assert next(c for c in checks if c.name == "Autostart").status == CheckStatus.OK

    def test_reflects_autostart_is_enabled_false(self):
        with patch("src.core.autostart.is_enabled", return_value=False):
            checks = run_diagnostics(_FakeSettings())
        assert next(c for c in checks if c.name == "Autostart").status == CheckStatus.WARN


class TestFormatReport:
    def test_includes_header_and_every_check(self):
        checks = [
            DiagnosticCheck("Python", CheckStatus.OK, "3.11.9"),
            DiagnosticCheck("Assets", CheckStatus.FAIL, "não encontrado"),
        ]
        report = format_report(checks)
        assert "SILVA DIAGNOSTICS" in report
        assert "✓ Python — 3.11.9" in report
        assert "✗ Assets — não encontrado" in report

    def test_check_without_detail_has_no_trailing_dash(self):
        report = format_report([DiagnosticCheck("Qt", CheckStatus.OK)])
        assert "Qt —" not in report
