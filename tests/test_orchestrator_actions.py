from unittest.mock import MagicMock

from src.core.orchestrator import CompanionOrchestrator


def _bare_orchestrator():
    """Builds an orchestrator without running __init__ (which needs sprites, AI keys, etc.),
    just to unit-test the action-dispatch logic in isolation."""
    orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
    orch.action_manager = MagicMock()
    orch.memory_manager = MagicMock()
    return orch


class TestExecuteAction:
    def test_open_application(self):
        orch = _bare_orchestrator()
        handled = orch._execute_action("open_application", "chrome")
        orch.action_manager.open_application.assert_called_once_with("chrome")
        assert handled is True

    def test_open_url(self):
        orch = _bare_orchestrator()
        orch._execute_action("open_url", "https://example.com")
        orch.action_manager.open_url.assert_called_once_with("https://example.com")

    def test_search_web(self):
        orch = _bare_orchestrator()
        orch._execute_action("search_web", "python")
        orch.action_manager.search_web.assert_called_once_with("python")

    def test_remember_with_valid_dict(self):
        orch = _bare_orchestrator()
        orch._execute_action("remember", {"key": "cor_favorita", "value": "roxo"})
        orch.memory_manager.remember.assert_called_once_with("cor_favorita", "roxo")

    def test_remember_without_key_is_ignored(self):
        orch = _bare_orchestrator()
        handled = orch._execute_action("remember", {"value": "roxo"})
        orch.memory_manager.remember.assert_not_called()
        assert handled is False

    def test_forget_memory_with_dict_param(self):
        orch = _bare_orchestrator()
        orch._execute_action("forget_memory", {"key": "cor_favorita"})
        orch.memory_manager.forget.assert_called_once_with("cor_favorita")

    def test_forget_memory_with_plain_string_param(self):
        orch = _bare_orchestrator()
        orch._execute_action("forget_memory", "cor_favorita")
        orch.memory_manager.forget.assert_called_once_with("cor_favorita")

    def test_no_action_does_nothing(self):
        orch = _bare_orchestrator()
        handled = orch._execute_action("Nenhuma", "")
        orch.action_manager.open_application.assert_not_called()
        orch.memory_manager.remember.assert_not_called()
        orch.memory_manager.forget.assert_not_called()
        assert handled is False

    def test_unknown_action_is_ignored_safely(self):
        orch = _bare_orchestrator()
        assert orch._execute_action("fly_to_moon", "now") is False

    def test_action_without_param_is_ignored(self):
        orch = _bare_orchestrator()
        orch._execute_action("open_application", "")
        orch.action_manager.open_application.assert_not_called()


def _bare_orchestrator_with_settings(**settings_overrides):
    orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
    defaults = {"screen_monitoring_enabled": True, "private_mode": False}
    defaults.update(settings_overrides)
    orch.settings = MagicMock()
    orch.settings.get.side_effect = lambda key, default=None: defaults.get(key, default)
    return orch


class TestShouldAttachVision:
    def test_attaches_when_available_and_message_mentions_screen(self):
        orch = _bare_orchestrator_with_settings()
        assert orch._should_attach_vision("o que tem na minha tela agora?") is True

    def test_does_not_attach_for_generic_chit_chat(self):
        """Regression test: vision used to attach on every message, adding ~50s of
        latency to simple messages like 'oi, tudo bem?' via the slower vision model."""
        orch = _bare_orchestrator_with_settings()
        assert orch._should_attach_vision("oi, tudo bem?") is False

    def test_does_not_attach_when_vision_disabled(self):
        orch = _bare_orchestrator_with_settings(screen_monitoring_enabled=False)
        assert orch._should_attach_vision("o que tem na minha tela?") is False

    def test_does_not_attach_in_private_mode(self):
        orch = _bare_orchestrator_with_settings(private_mode=True)
        assert orch._should_attach_vision("o que tem na minha tela?") is False

    def test_translate_keyword_also_triggers_vision(self):
        orch = _bare_orchestrator_with_settings()
        assert orch._should_attach_vision("traduz isso pra mim") is True


class FakeSettings:
    """Minimal in-memory stand-in for Settings, so set_full_vision's effects can be
    asserted directly instead of scripting a MagicMock's side_effect by hand."""

    def __init__(self, **kwargs):
        self.data = dict(kwargs)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def _bare_orchestrator_with_full_vision_deps(**settings_overrides):
    orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
    defaults = {"screen_monitoring_enabled": False, "private_mode": True, "screen_interval_seconds": 2.0}
    defaults.update(settings_overrides)
    orch.settings = FakeSettings(**defaults)
    orch.vision_timer = MagicMock()
    orch.vision_timer.isActive.return_value = defaults["screen_monitoring_enabled"]
    return orch


class TestSetFullVision:
    def test_enabling_clears_private_mode_and_starts_timer(self):
        orch = _bare_orchestrator_with_full_vision_deps()
        orch.set_full_vision(True)
        assert orch.settings.get("private_mode") is False
        assert orch.settings.get("screen_monitoring_enabled") is True
        orch.vision_timer.start.assert_called_once()

    def test_disabling_restores_private_mode_and_stops_timer(self):
        orch = _bare_orchestrator_with_full_vision_deps(screen_monitoring_enabled=True, private_mode=False)
        orch.set_full_vision(False)
        assert orch.settings.get("private_mode") is True
        assert orch.settings.get("screen_monitoring_enabled") is False
        orch.vision_timer.stop.assert_called_once()

    def test_enabling_when_timer_already_active_does_not_restart(self):
        orch = _bare_orchestrator_with_full_vision_deps(screen_monitoring_enabled=True)
        orch.set_full_vision(True)
        orch.vision_timer.start.assert_not_called()


class TestMaybeActivateVisionCommand:
    def test_phrase_triggers_full_vision(self):
        orch = _bare_orchestrator_with_full_vision_deps()
        orch._maybe_activate_vision_command("ei, ver minha tela agora")
        assert orch.settings.get("screen_monitoring_enabled") is True
        assert orch.settings.get("private_mode") is False

    def test_unrelated_message_does_not_trigger(self):
        orch = _bare_orchestrator_with_full_vision_deps()
        orch._maybe_activate_vision_command("oi, tudo bem?")
        assert orch.settings.get("screen_monitoring_enabled") is False
        orch.vision_timer.start.assert_not_called()

    def test_phrase_is_case_insensitive(self):
        orch = _bare_orchestrator_with_full_vision_deps()
        orch._maybe_activate_vision_command("VER MINHA TELA")
        assert orch.settings.get("screen_monitoring_enabled") is True
