import time
from unittest.mock import MagicMock

from PySide6.QtCore import QTimer

from src.core.orchestrator import (
    CompanionOrchestrator, SPONTANEOUS_TALK_PROMPT, MAX_HEADLINE_OFFERS,
    NERD_SPONTANEOUS_TALK_IDLE_GAP_S, NERD_SPONTANEOUS_TALK_CHECK_INTERVAL_S,
)
from src.core.event_bus import EventBus
from src.core.agent_core import AgentCore
from src.core.tool_registry import build_default_registry
from src.vision.continuous_vision import ContinuousVisionBuffer, VisionMode


def _bare_orchestrator():
    """Builds an orchestrator without running __init__ (which needs sprites, AI keys, etc.),
    just to unit-test the action-dispatch logic in isolation."""
    orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
    orch.action_manager = MagicMock()
    orch.memory_manager = MagicMock()
    orch.event_bus = EventBus()
    orch.agent_core = AgentCore(build_default_registry(orch.action_manager, orch.memory_manager), orch.event_bus)
    return orch


def _capture(event_bus, event_type):
    """Subscribes a list to an EventBus topic and returns it; captured kwargs append live."""
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


class TestOnAppResolved:
    def test_emits_app_auto_resolved_without_touching_settings(self):
        """Regression guard: _on_app_resolved must only notify (via the event
        bus), never write the resolved app back into settings.allowlist —
        doing so used to grant permanent permission for an app the user never
        explicitly approved."""
        orch = _bare_orchestrator()
        orch.settings = MagicMock()
        received = _capture(orch.event_bus, "APP_AUTO_RESOLVED")

        orch._on_app_resolved("firefox", r"C:\firefox.exe")

        assert received == [{"app_name": "firefox", "command": r"C:\firefox.exe"}]
        orch.settings.set.assert_not_called()


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


class TestExecuteActionEvents:
    """Regression tests for the Event Bus adoption pass: ACTION_REQUESTED/EXECUTED/
    REJECTED must reflect what actually happened, not just that dispatch was attempted."""

    def test_successful_action_emits_requested_then_executed(self):
        orch = _bare_orchestrator()
        orch.action_manager.open_application.return_value = True
        requested = _capture(orch.event_bus, "ACTION_REQUESTED")
        executed = _capture(orch.event_bus, "ACTION_EXECUTED")
        rejected = _capture(orch.event_bus, "ACTION_REJECTED")

        orch._execute_action("open_application", "chrome")

        assert requested == [{"action": "open_application", "action_param": "chrome"}]
        assert executed == [{"action": "open_application", "action_param": "chrome"}]
        assert rejected == []

    def test_failed_action_emits_rejected_not_executed(self):
        """e.g. the app wasn't in the allowlist — open_application() itself returned False."""
        orch = _bare_orchestrator()
        orch.action_manager.open_application.return_value = False
        executed = _capture(orch.event_bus, "ACTION_EXECUTED")
        rejected = _capture(orch.event_bus, "ACTION_REJECTED")

        handled = orch._execute_action("open_application", "not_allowed_app")

        assert handled is False
        assert executed == []
        assert len(rejected) == 1

    def test_no_action_emits_nothing(self):
        orch = _bare_orchestrator()
        requested = _capture(orch.event_bus, "ACTION_REQUESTED")

        orch._execute_action("Nenhuma", "")

        assert requested == []


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
    orch.event_bus = EventBus()
    # A real QTimer, not a MagicMock: set_vision_monitoring dispatches start()/stop()
    # through QMetaObject.invokeMethod (needed so it's safe to call from a worker
    # thread or the `keyboard` hotkey thread), which requires a real QObject.
    orch.vision_timer = QTimer()
    if defaults["screen_monitoring_enabled"]:
        orch.vision_timer.start(int(defaults["screen_interval_seconds"] * 1000))
    return orch


class TestSetFullVision:
    def test_enabling_clears_private_mode_and_starts_timer(self):
        orch = _bare_orchestrator_with_full_vision_deps()
        orch.set_full_vision(True)
        assert orch.settings.get("private_mode") is False
        assert orch.settings.get("screen_monitoring_enabled") is True
        assert orch.vision_timer.isActive()

    def test_disabling_restores_private_mode_and_stops_timer(self):
        orch = _bare_orchestrator_with_full_vision_deps(screen_monitoring_enabled=True, private_mode=False)
        orch.set_full_vision(False)
        assert orch.settings.get("private_mode") is True
        assert orch.settings.get("screen_monitoring_enabled") is False
        assert not orch.vision_timer.isActive()

    def test_enabling_when_timer_already_active_keeps_it_active(self):
        orch = _bare_orchestrator_with_full_vision_deps(screen_monitoring_enabled=True)
        orch.set_full_vision(True)
        assert orch.vision_timer.isActive()

    def test_emits_vision_monitoring_toggled_event(self):
        """Regression test: set_full_vision is called directly by the "-" hotkey,
        tray menu, and "minha tela" command — none of them go through
        handle_user_message, so without this event the toggle happened with zero
        user-visible feedback."""
        orch = _bare_orchestrator_with_full_vision_deps()
        received = _capture(orch.event_bus, "VISION_MONITORING_TOGGLED")

        orch.set_full_vision(True)

        assert received == [{"enabled": True}]


class TestMaybeActivateVisionCommand:
    def test_short_phrase_triggers_full_vision(self):
        """The trigger was shortened from 'ver minha tela' to just 'minha tela'."""
        orch = _bare_orchestrator_with_full_vision_deps()
        orch._maybe_activate_vision_command("ei, minha tela tá travando")
        assert orch.settings.get("screen_monitoring_enabled") is True
        assert orch.settings.get("private_mode") is False

    def test_old_longer_phrase_still_works(self):
        """'ver minha tela' contains 'minha tela' as a substring, so it still triggers."""
        orch = _bare_orchestrator_with_full_vision_deps()
        orch._maybe_activate_vision_command("ei, ver minha tela agora")
        assert orch.settings.get("screen_monitoring_enabled") is True

    def test_unrelated_message_does_not_trigger(self):
        orch = _bare_orchestrator_with_full_vision_deps()
        orch._maybe_activate_vision_command("oi, tudo bem?")
        assert orch.settings.get("screen_monitoring_enabled") is False
        assert not orch.vision_timer.isActive()

    def test_phrase_is_case_insensitive(self):
        orch = _bare_orchestrator_with_full_vision_deps()
        orch._maybe_activate_vision_command("MINHA TELA")
        assert orch.settings.get("screen_monitoring_enabled") is True


class TestSelectProvider:
    """Regression tests: a smaller vision-capable model used to be the default
    for EVERY message, and was unreliable at following the action/JSON format
    (e.g. refusing plain 'abre o chrome' requests). Ordinary messages must always
    get the strong text model; only vision-relevant ones pay the vision-model cost."""

    def test_uses_text_provider_when_vision_not_needed(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.ai_provider = MagicMock(name="text_provider")
        orch.ai_vision_provider = MagicMock(name="vision_provider")

        assert orch._select_provider(vision_needed=False) is orch.ai_provider

    def test_uses_vision_provider_when_needed_and_available(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.ai_provider = MagicMock(name="text_provider")
        orch.ai_vision_provider = MagicMock(name="vision_provider")

        assert orch._select_provider(vision_needed=True) is orch.ai_vision_provider

    def test_falls_back_to_text_provider_when_no_vision_provider_available(self):
        """e.g. Ollama, which doesn't have a configured vision option yet."""
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.ai_provider = MagicMock(name="text_provider")
        orch.ai_vision_provider = None

        assert orch._select_provider(vision_needed=True) is orch.ai_provider

    def test_uses_complex_provider_when_needed_and_available(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.ai_provider = MagicMock(name="text_provider")
        orch.ai_vision_provider = None
        orch.ai_complex_provider = MagicMock(name="complex_provider")

        assert orch._select_provider(vision_needed=False, complex_needed=True) is orch.ai_complex_provider

    def test_falls_back_to_text_provider_when_no_complex_provider_available(self):
        """e.g. Ollama, which doesn't have a configured strong-model option yet."""
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.ai_provider = MagicMock(name="text_provider")
        orch.ai_vision_provider = None
        orch.ai_complex_provider = None

        assert orch._select_provider(vision_needed=False, complex_needed=True) is orch.ai_provider

    def test_vision_takes_priority_over_complex(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.ai_provider = MagicMock(name="text_provider")
        orch.ai_vision_provider = MagicMock(name="vision_provider")
        orch.ai_complex_provider = MagicMock(name="complex_provider")

        assert orch._select_provider(vision_needed=True, complex_needed=True) is orch.ai_vision_provider


class TestIsComplexQuery:
    def _orch(self):
        return CompanionOrchestrator.__new__(CompanionOrchestrator)

    def test_short_simple_message_is_not_complex(self):
        orch = self._orch()
        assert orch._is_complex_query("abre o chrome") is False

    def test_greeting_is_not_complex(self):
        orch = self._orch()
        assert orch._is_complex_query("oi, tudo bem?") is False

    def test_explanation_keyword_is_complex(self):
        orch = self._orch()
        assert orch._is_complex_query("explica como funciona a fusão nuclear") is True

    def test_why_question_is_complex(self):
        orch = self._orch()
        assert orch._is_complex_query("por que o céu é azul?") is True

    def test_keyword_match_is_case_insensitive(self):
        orch = self._orch()
        assert orch._is_complex_query("EXPLIQUE isso pra mim") is True

    def test_long_message_without_keyword_is_still_complex(self):
        orch = self._orch()
        long_text = " ".join(["palavra"] * 30)
        assert orch._is_complex_query(long_text) is True

    def test_short_message_without_keyword_is_not_complex(self):
        orch = self._orch()
        short_text = " ".join(["palavra"] * 5)
        assert orch._is_complex_query(short_text) is False


class TestInitComplexProvider:
    def _bare_orchestrator_with_settings(self, **settings_overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.settings = FakeSettings(**settings_overrides)
        return orch

    def test_nvidia_gets_a_strong_model(self):
        orch = self._bare_orchestrator_with_settings(ai_provider="nvidia", api_key="nvapi-x")
        provider = orch._init_complex_provider()
        assert provider is not None
        assert "70b" in provider.model

    def test_ollama_has_no_complex_provider(self):
        orch = self._bare_orchestrator_with_settings(ai_provider="ollama")
        assert orch._init_complex_provider() is None


class TestInitVisionProvider:
    def _bare_orchestrator_with_settings(self, **settings_overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.settings = FakeSettings(**settings_overrides)
        return orch

    def test_nvidia_provider_gets_a_vision_capable_model(self):
        orch = self._bare_orchestrator_with_settings(ai_provider="nvidia", api_key="nvapi-x")
        provider = orch._init_vision_provider()
        assert provider is not None
        assert provider.supports_vision()

    def test_ollama_has_no_vision_provider(self):
        orch = self._bare_orchestrator_with_settings(ai_provider="ollama")
        assert orch._init_vision_provider() is None


class TestMaybeActivateSystemAudioCommand:
    def _bare_orchestrator(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.system_audio_listener = MagicMock()
        return orch

    def test_som_do_jogo_phrase_activates_listening(self):
        orch = self._bare_orchestrator()
        orch._maybe_activate_system_audio_command("Silva, está ouvindo o som do jogo?")
        orch.system_audio_listener.set_enabled.assert_called_once_with(True)

    def test_som_do_pc_phrase_activates_listening(self):
        orch = self._bare_orchestrator()
        orch._maybe_activate_system_audio_command("está ouvindo o som do pc")
        orch.system_audio_listener.set_enabled.assert_called_once_with(True)

    def test_phrase_is_case_insensitive(self):
        orch = self._bare_orchestrator()
        orch._maybe_activate_system_audio_command("ESTÁ OUVINDO O SOM DO JOGO")
        orch.system_audio_listener.set_enabled.assert_called_once_with(True)

    def test_unrelated_message_does_not_trigger(self):
        orch = self._bare_orchestrator()
        orch._maybe_activate_system_audio_command("oi, tudo bem?")
        orch.system_audio_listener.set_enabled.assert_not_called()


class TestCheckScreenAndApp:
    def _bare_orchestrator(self, **settings_overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        defaults = {"screen_monitoring_enabled": False, "private_mode": True}
        defaults.update(settings_overrides)
        orch.settings = FakeSettings(**defaults)
        orch.event_bus = EventBus()
        orch.app_manager = MagicMock()
        orch.context_manager = MagicMock()
        orch.state_manager = MagicMock()
        orch.screen_capture = MagicMock()
        orch.change_detector = MagicMock()
        orch.vision_buffer = ContinuousVisionBuffer()
        orch._last_window_title = None
        orch._last_app_category = None
        orch._is_game_active = False
        return orch

    def _set_context(self, orch, title, category, is_game):
        orch.app_manager.detect_context.return_value = {
            "window_title": title, "category": category, "is_game": is_game
        }

    def test_game_started_emitted_and_state_set_to_gaming(self):
        orch = self._bare_orchestrator()
        self._set_context(orch, "Elden Ring", "gaming", True)
        started = _capture(orch.event_bus, "GAME_STARTED")

        orch._check_screen_and_app()

        assert len(started) == 1
        orch.state_manager.set_state.assert_any_call("GAMING", reason="Game detected")
        assert orch._is_game_active is True

    def test_game_ended_reverts_to_idle(self):
        """Regression test: GAMING used to never revert once a game closed — the
        character stayed stuck 'playing' indefinitely after the user closed it."""
        orch = self._bare_orchestrator()
        self._set_context(orch, "Elden Ring", "gaming", True)
        orch._check_screen_and_app()  # game starts

        self._set_context(orch, "Desktop", "general", False)
        ended = _capture(orch.event_bus, "GAME_ENDED")
        orch._check_screen_and_app()  # game ends

        assert len(ended) == 1
        orch.state_manager.set_state.assert_any_call("IDLE", reason="Game closed")
        assert orch._is_game_active is False

    def test_game_started_only_emitted_once_while_still_playing(self):
        orch = self._bare_orchestrator()
        self._set_context(orch, "Elden Ring", "gaming", True)
        started = _capture(orch.event_bus, "GAME_STARTED")

        orch._check_screen_and_app()
        orch._check_screen_and_app()
        orch._check_screen_and_app()

        assert len(started) == 1

    def test_window_changed_only_on_actual_change(self):
        orch = self._bare_orchestrator()
        self._set_context(orch, "Notepad", "general", False)
        changed = _capture(orch.event_bus, "WINDOW_CHANGED")

        orch._check_screen_and_app()
        orch._check_screen_and_app()  # same title again

        assert len(changed) == 1

    def test_application_changed_on_category_change(self):
        orch = self._bare_orchestrator()
        changed = _capture(orch.event_bus, "APPLICATION_CHANGED")

        self._set_context(orch, "main.py - VS Code", "coding", False)
        orch._check_screen_and_app()

        self._set_context(orch, "YouTube - Chrome", "browser", False)
        orch._check_screen_and_app()

        assert len(changed) == 2  # None -> coding, coding -> browser

    def test_screen_changed_only_when_monitoring_and_not_private(self):
        orch = self._bare_orchestrator(screen_monitoring_enabled=True, private_mode=False)
        self._set_context(orch, "Game", "gaming", False)
        orch.change_detector.has_changed.return_value = True
        changed = _capture(orch.event_bus, "SCREEN_CHANGED")

        orch._check_screen_and_app()

        assert len(changed) == 1

    def test_screen_changed_not_emitted_in_private_mode(self):
        orch = self._bare_orchestrator(screen_monitoring_enabled=True, private_mode=True)
        self._set_context(orch, "Game", "gaming", False)
        changed = _capture(orch.event_bus, "SCREEN_CHANGED")

        orch._check_screen_and_app()

        assert changed == []
        orch.screen_capture.capture_primary.assert_not_called()

    def test_screen_context_is_updated_every_tick_even_without_a_change(self):
        """FASE 11 needs a fresh timestamp on every tick (not just on actual
        change) to measure staleness accurately — a real ContextManager
        stands in here since this behavior is about *what* gets passed to it."""
        from src.ai.context import ContextManager
        orch = self._bare_orchestrator(screen_monitoring_enabled=True, private_mode=False)
        orch.context_manager = ContextManager()
        self._set_context(orch, "Game", "gaming", False)
        orch.change_detector.has_changed.return_value = False

        orch._check_screen_and_app()

        assert orch.context_manager.screen_context["window_title"] == "Game"
        assert orch.context_manager.screen_context["changed"] is False
        assert "timestamp" in orch.context_manager.screen_context

    def test_vision_buffer_receives_an_entry_when_a_mode_is_active(self):
        orch = self._bare_orchestrator(screen_monitoring_enabled=True, private_mode=False)
        self._set_context(orch, "Game", "gaming", False)

        orch._check_screen_and_app()

        assert orch.vision_buffer.freshest().window_title == "Game"

    def test_vision_buffer_receives_nothing_when_mode_is_off(self):
        orch = self._bare_orchestrator(screen_monitoring_enabled=False)
        self._set_context(orch, "Game", "gaming", False)

        orch._check_screen_and_app()

        assert orch.vision_buffer.freshest() is None


class TestComputeVisionMode:
    def _bare(self, **settings_overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.settings = FakeSettings(**settings_overrides)
        return orch

    def test_defaults_to_off(self):
        assert self._bare()._compute_vision_mode() == VisionMode.OFF

    def test_monitoring_disabled_is_off_even_if_not_private(self):
        orch = self._bare(screen_monitoring_enabled=False, private_mode=False)
        assert orch._compute_vision_mode() == VisionMode.OFF

    def test_private_mode_is_off_regardless_of_monitoring(self):
        """Matches the UI's own promise for this checkbox: 'Modo Privado
        (Nenhuma captura ou OCR)' — private_mode=True must mean zero capture,
        not a lighter CONTEXT-only mode."""
        orch = self._bare(screen_monitoring_enabled=True, private_mode=True)
        assert orch._compute_vision_mode() == VisionMode.OFF

    def test_monitoring_enabled_and_not_private_is_active(self):
        orch = self._bare(screen_monitoring_enabled=True, private_mode=False)
        assert orch._compute_vision_mode() == VisionMode.ACTIVE

    def test_explicit_setting_overrides_legacy_toggles(self):
        orch = self._bare(screen_monitoring_enabled=False, screen_vision_mode="AWARENESS")
        assert orch._compute_vision_mode() == VisionMode.AWARENESS

    def test_invalid_explicit_setting_falls_back_to_legacy_toggles(self):
        orch = self._bare(screen_monitoring_enabled=True, private_mode=False, screen_vision_mode="not_a_real_mode")
        assert orch._compute_vision_mode() == VisionMode.ACTIVE


class _SyncThread:
    """Stand-in for threading.Thread that runs its target immediately and
    synchronously on .start(), so worker-thread effects can be asserted on
    directly instead of racing a real background thread."""

    def __init__(self, target=None, args=(), kwargs=None, **_ignored):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


class TestHandleUserMessageErrorHandling:
    """Regression tests: an uncaught exception anywhere in the worker used to
    silently kill the background thread, leaving the character stuck in
    THINKING forever with no feedback to the user."""

    def _bare_orchestrator(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.event_bus = EventBus()
        orch.state_manager = MagicMock()
        orch.memory_manager = MagicMock()
        orch.memory_manager.get_memories.return_value = {}
        orch.memory_manager.get_history.return_value = []
        orch.context_manager = MagicMock()
        orch.context_manager.build_prompt_context.return_value = "prompt"
        orch.settings = FakeSettings(screen_monitoring_enabled=False, private_mode=True)
        orch.screen_capture = MagicMock()
        orch.ai_provider = MagicMock()
        orch.ai_vision_provider = None
        orch.action_manager = MagicMock()
        orch.tts = MagicMock()
        orch.system_audio_listener = MagicMock()
        orch.agent_core = AgentCore(build_default_registry(orch.action_manager, orch.memory_manager), orch.event_bus)
        return orch

    def test_provider_exception_recovers_instead_of_hanging(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.side_effect = RuntimeError("network down")
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        errors = _capture(orch.event_bus, "ERROR_OCCURRED")
        responses = []

        orch.handle_user_message("oi", on_response=lambda r: responses.append(r))

        assert len(errors) == 1
        assert len(responses) == 1 and responses[0]  # got a fallback message, not silence
        orch.state_manager.set_state.assert_any_call("CONFUSED", reason="Internal error")

    def test_successful_message_still_works_with_sync_thread(self, monkeypatch):
        """Sanity check that _SyncThread itself isn't what's causing success below —
        confirms the happy path is unaffected by the new try/except wrapper."""
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "Oi!", "animation": "HAPPY", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        errors = _capture(orch.event_bus, "ERROR_OCCURRED")
        responses = []

        orch.handle_user_message("oi", on_response=lambda r: responses.append(r))

        assert errors == []
        assert responses == ["Oi!"]

    def test_updates_last_interaction_time(self, monkeypatch):
        """So _maybe_speak_spontaneously knows not to talk over a fresh exchange."""
        import threading
        import json
        orch = self._bare_orchestrator()
        orch._last_interaction_time = 0.0
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "Oi!", "animation": "HAPPY", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        before = time.monotonic()
        orch.handle_user_message("oi")

        assert orch._last_interaction_time >= before


class TestHandleUserMessageNerdShortCircuit:
    """A nerd mode toggle command must never reach the AI provider — it's a
    pure command with a deterministic reply, not a question."""

    def _bare_orchestrator(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.event_bus = EventBus()
        orch.state_manager = MagicMock()
        orch.memory_manager = MagicMock()
        orch.settings = FakeSettings()
        orch.nerd_mode_enabled = False
        orch.tts = MagicMock()
        orch._last_interaction_time = 0.0
        orch.ai_provider = MagicMock()
        return orch

    def test_enable_command_speaks_confirmation_without_calling_ai(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        responses = []

        orch.handle_user_message("Silva, vira nerd", on_response=lambda r: responses.append(r))

        assert responses == ["Modo Nerd ativado."]
        orch.ai_provider.chat.assert_not_called()
        assert orch.nerd_mode_enabled is True

    def test_disable_command_speaks_confirmation_without_calling_ai(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        orch.nerd_mode_enabled = True
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        responses = []

        orch.handle_user_message("desliga o modo nerd", on_response=lambda r: responses.append(r))

        assert responses == ["Modo Nerd desativado."]
        orch.ai_provider.chat.assert_not_called()
        assert orch.nerd_mode_enabled is False

    def test_confirmation_is_recorded_into_history(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("ativa o modo nerd")

        orch.memory_manager.record_turn.assert_called_once_with("ativa o modo nerd", "Modo Nerd ativado.")

    def test_ordinary_message_still_reaches_the_ai(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.memory_manager.get_memories.return_value = {}
        orch.memory_manager.get_history.return_value = []
        orch.context_manager = MagicMock()
        orch.context_manager.build_prompt_context.return_value = "prompt"
        orch.screen_capture = MagicMock()
        orch.ai_vision_provider = None
        orch.action_manager = MagicMock()
        orch.system_audio_listener = MagicMock()
        orch.agent_core = AgentCore(build_default_registry(orch.action_manager, orch.memory_manager), orch.event_bus)
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "oi!", "animation": "HAPPY", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("oi, tudo bem?")

        orch.ai_provider.chat.assert_called_once()


class TestHandleUserMessageIsDirectInput:
    """FASE 15 — REGRA FUNDAMENTAL: content Silva only overheard (system
    audio) must never gain the same command authority as something the user
    actually said/typed. is_direct_input=False (used only by the system-audio
    call site in app.py) must skip every deterministic keyword-triggered side
    effect below, while the AI still gets to see and react to the text
    normally."""

    def _bare_orchestrator(self, **settings_overrides):
        import json
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.event_bus = EventBus()
        orch.state_manager = MagicMock()
        orch.memory_manager = MagicMock()
        orch.memory_manager.get_memories.return_value = {}
        orch.memory_manager.get_history.return_value = []
        orch.context_manager = MagicMock()
        orch.context_manager.build_prompt_context.return_value = "prompt"
        orch.settings = FakeSettings(screen_monitoring_enabled=False, private_mode=True, **settings_overrides)
        orch.screen_capture = MagicMock()
        orch.ai_provider = MagicMock()
        orch.ai_vision_provider = None
        orch.action_manager = MagicMock()
        orch.tts = MagicMock()
        orch.system_audio_listener = MagicMock()
        orch.translation_manager = MagicMock()
        orch.nerd_mode_enabled = False
        orch.spontaneous_talk_enabled = True
        orch._last_interaction_time = 0.0
        orch.agent_core = AgentCore(build_default_registry(orch.action_manager, orch.memory_manager), orch.event_bus)
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "oi!", "animation": "HAPPY", "action": "Nenhuma", "action_param": ""
        })
        return orch

    def test_overheard_nerd_command_does_not_toggle_nerd_mode(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("[Áudio do jogo/PC]: Silva, vira nerd", is_direct_input=False)

        assert orch.nerd_mode_enabled is False
        orch.ai_provider.chat.assert_called_once()  # went to the AI as ordinary content instead

    def test_overheard_vision_activation_phrase_does_not_enable_vision(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("[Áudio do jogo/PC]: dá uma olhada na minha tela", is_direct_input=False)

        assert orch.settings.get("screen_monitoring_enabled") is False

    def test_overheard_system_audio_activation_phrase_does_not_enable_listening(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("[Áudio do jogo/PC]: está ouvindo o som do jogo", is_direct_input=False)

        orch.system_audio_listener.set_enabled.assert_not_called()

    def test_overheard_spontaneous_talk_disable_phrase_is_ignored(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("[Áudio do jogo/PC]: pare de falar aleatoriamente", is_direct_input=False)

        assert orch.spontaneous_talk_enabled is True

    def test_overheard_traduz_keyword_does_not_trigger_ocr(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("[Áudio do jogo/PC]: e agora traduz isso aqui pra mim", is_direct_input=False)

        orch.translation_manager.translate_current_screen.assert_not_called()

    def test_overheard_content_still_reaches_the_ai_normally(self, monkeypatch):
        """The point isn't to silence system audio — Silva can still comment
        on/react to it — only the deterministic side effects are gated."""
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        responses = []

        orch.handle_user_message(
            "[Áudio do jogo/PC]: que jogo incrível", on_response=lambda r: responses.append(r), is_direct_input=False,
        )

        assert responses == ["oi!"]

    def test_direct_input_default_still_triggers_nerd_toggle(self, monkeypatch):
        """Regression guard: the default (is_direct_input=True) must keep
        working exactly like before this change for real user speech/text."""
        import threading
        orch = self._bare_orchestrator()
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch.handle_user_message("Silva, vira nerd")

        assert orch.nerd_mode_enabled is True
        orch.ai_provider.chat.assert_not_called()  # still the deterministic short-circuit, no AI call


class TestInitTtsProvider:
    def _bare_orchestrator(self, **settings_overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.settings = FakeSettings(**settings_overrides)
        return orch

    def test_defaults_to_edge_tts_with_a_pyttsx3_fallback(self):
        from src.voice.tts import EdgeTTSProvider, FallbackTTSProvider, Pyttsx3Provider
        orch = self._bare_orchestrator()
        provider = orch._init_tts_provider()
        assert isinstance(provider, FallbackTTSProvider)
        assert isinstance(provider.primary, EdgeTTSProvider)
        assert isinstance(provider.fallback, Pyttsx3Provider)

    def test_pyttsx3_selected_when_configured(self):
        from src.voice.tts import Pyttsx3Provider
        orch = self._bare_orchestrator(voice_provider="pyttsx3")
        assert isinstance(orch._init_tts_provider(), Pyttsx3Provider)


class TestDefaultTextModelIsFast:
    def test_default_text_model_is_the_faster_8b_variant(self):
        """Regression test: the 70b default took ~8s per reply even for 'oi, tudo
        bem?' (measured live); 8b answers the same in ~3s with the same reliability
        given the JSON examples now baked into the system prompt."""
        from src.core.orchestrator import DEFAULT_TEXT_MODEL
        assert DEFAULT_TEXT_MODEL == "meta/llama-3.1-8b-instruct"

    def test_nvidia_provider_uses_the_fast_default_model(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.settings = FakeSettings(ai_provider="nvidia", api_key="nvapi-x")
        provider = orch._init_ai_provider()
        assert provider.model == "meta/llama-3.1-8b-instruct"


class TestMaybeToggleSpontaneousTalk:
    def _bare_orchestrator(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.spontaneous_talk_enabled = True
        orch.settings = FakeSettings()
        return orch

    def test_disable_phrase_turns_it_off(self):
        orch = self._bare_orchestrator()
        orch._maybe_toggle_spontaneous_talk("Silva, pare de falar aleatoriamente por favor")
        assert orch.spontaneous_talk_enabled is False
        assert orch.settings.get("spontaneous_talk_enabled") is False

    def test_enable_phrase_turns_it_back_on(self):
        orch = self._bare_orchestrator()
        orch.spontaneous_talk_enabled = False
        orch._maybe_toggle_spontaneous_talk("ativar falar aleatoriamente")
        assert orch.spontaneous_talk_enabled is True
        assert orch.settings.get("spontaneous_talk_enabled") is True

    def test_unrelated_message_does_not_change_state(self):
        orch = self._bare_orchestrator()
        orch._maybe_toggle_spontaneous_talk("oi, tudo bem?")
        assert orch.spontaneous_talk_enabled is True

    def test_phrase_is_case_insensitive(self):
        orch = self._bare_orchestrator()
        orch._maybe_toggle_spontaneous_talk("PARE DE FALAR ALEATORIAMENTE")
        assert orch.spontaneous_talk_enabled is False


class TestMaybeToggleNerdMode:
    def _bare_orchestrator(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.nerd_mode_enabled = False
        orch.settings = FakeSettings()
        orch.event_bus = EventBus()
        orch.state_manager = MagicMock()
        return orch

    def test_enable_phrase_turns_it_on_and_returns_confirmation(self):
        orch = self._bare_orchestrator()

        reply = orch._maybe_toggle_nerd_mode("Silva, vira nerd")

        assert orch.nerd_mode_enabled is True
        assert orch.settings.get("nerd_mode_enabled") is True
        assert reply == "Modo Nerd ativado."
        orch.state_manager.set_state.assert_called_once_with("NERD_ACTIVE", reason="Nerd mode enabled")

    def test_disable_phrase_turns_it_off_and_returns_confirmation(self):
        orch = self._bare_orchestrator()
        orch.nerd_mode_enabled = True

        reply = orch._maybe_toggle_nerd_mode("desliga o modo nerd")

        assert orch.nerd_mode_enabled is False
        assert orch.settings.get("nerd_mode_enabled") is False
        assert reply == "Modo Nerd desativado."
        orch.state_manager.set_state.assert_called_once_with("IDLE", reason="Nerd mode disabled")

    def test_bare_modo_nerd_phrase_also_enables(self):
        orch = self._bare_orchestrator()
        reply = orch._maybe_toggle_nerd_mode("modo nerd")
        assert orch.nerd_mode_enabled is True
        assert reply == "Modo Nerd ativado."

    def test_vira_nerd_phrase_also_enables(self):
        orch = self._bare_orchestrator()
        reply = orch._maybe_toggle_nerd_mode("Silva, vira nerd")
        assert orch.nerd_mode_enabled is True
        assert reply == "Modo Nerd ativado."

    def test_unrelated_message_returns_none_and_does_not_change_state(self):
        orch = self._bare_orchestrator()

        reply = orch._maybe_toggle_nerd_mode("oi, tudo bem?")

        assert reply is None
        assert orch.nerd_mode_enabled is False
        orch.state_manager.set_state.assert_not_called()

    def test_emits_nerd_mode_toggled_event(self):
        orch = self._bare_orchestrator()
        received = _capture(orch.event_bus, "NERD_MODE_TOGGLED")

        orch._maybe_toggle_nerd_mode("ativa o modo nerd")

        assert received == [{"enabled": True}]


class TestMaybeSpeakSpontaneously:
    def _bare_orchestrator(self, **overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.spontaneous_talk_enabled = overrides.pop("spontaneous_talk_enabled", True)
        orch.nerd_mode_enabled = overrides.pop("nerd_mode_enabled", False)
        orch.state_machine = MagicMock()
        orch.state_machine.get_state.return_value = overrides.pop("state", "IDLE")
        orch._last_interaction_time = overrides.pop("last_interaction_time", time.monotonic() - 10_000)
        orch._last_spontaneous_time = overrides.pop("last_spontaneous_time", 0.0)
        orch._trigger_spontaneous_comment = MagicMock()
        return orch

    def test_does_not_trigger_when_disabled(self):
        orch = self._bare_orchestrator(spontaneous_talk_enabled=False)
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_not_called()

    def test_does_not_trigger_while_thinking(self):
        orch = self._bare_orchestrator(state="THINKING")
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_not_called()

    def test_does_not_trigger_while_listening(self):
        orch = self._bare_orchestrator(state="LISTENING")
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_not_called()

    def test_does_not_trigger_soon_after_user_interaction(self):
        """So it never talks over a conversation that just happened."""
        orch = self._bare_orchestrator(last_interaction_time=time.monotonic())
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_not_called()

    def test_does_not_trigger_too_soon_after_last_spontaneous_comment(self):
        orch = self._bare_orchestrator(last_spontaneous_time=time.monotonic())
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_not_called()

    def test_triggers_when_all_conditions_are_met(self):
        orch = self._bare_orchestrator()
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_called_once()


class TestBuildNewsContext:
    def _orch(self, headlines):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.news_provider = MagicMock()
        orch.news_provider.get_headlines.return_value = headlines
        orch._headline_offer_counts = {}
        return orch

    def test_empty_headlines_returns_empty_string(self):
        orch = self._orch({"brasil": [], "mundo": []})
        assert orch._build_news_context() == ""

    def test_first_headline_per_feed_is_flagged_destaque(self):
        orch = self._orch({"brasil": ["Manchete A", "Manchete B"], "mundo": ["World A"]})

        result = orch._build_news_context()

        assert "[DESTAQUE] Manchete A" in result
        assert "- Manchete B" in result and "[DESTAQUE] Manchete B" not in result
        assert "[DESTAQUE] World A" in result

    def test_headline_keeps_being_offered_across_multiple_checks(self):
        """A single offer used to permanently consume a headline, so if the
        (fast, not fully reliable) model picked a different topic that one time,
        the story never came up again — it now gets several chances."""
        orch = self._orch({"brasil": ["Manchete A"], "mundo": []})

        first = orch._build_news_context()
        second = orch._build_news_context()

        assert "Manchete A" in first
        assert "Manchete A" in second

    def test_headline_stops_being_offered_after_max_offers(self):
        orch = self._orch({"brasil": ["Manchete A"], "mundo": []})

        for _ in range(MAX_HEADLINE_OFFERS):
            result = orch._build_news_context()
            assert "Manchete A" in result

        assert orch._build_news_context() == ""

    def test_offering_headlines_updates_offer_counts(self):
        orch = self._orch({"brasil": ["Manchete A"], "mundo": []})
        orch._build_news_context()
        assert orch._headline_offer_counts["Manchete A"] == 1

    def test_only_headlines_under_the_offer_limit_are_included(self):
        orch = self._orch({"brasil": ["Manchete A", "Manchete B"], "mundo": []})
        orch._headline_offer_counts = {"Manchete A": MAX_HEADLINE_OFFERS}

        result = orch._build_news_context()

        assert "Manchete A" not in result
        assert "Manchete B" in result


class TestTriggerSpontaneousComment:
    def _bare_orchestrator(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.event_bus = EventBus()
        orch.memory_manager = MagicMock()
        orch.memory_manager.get_history.return_value = []
        orch.memory_manager.get_memories.return_value = {}
        orch.context_manager = MagicMock()
        orch.context_manager.build_prompt_context.return_value = "prompt"
        orch.ai_provider = MagicMock()
        orch.state_manager = MagicMock()
        orch.tts = MagicMock()
        orch.settings = FakeSettings()
        orch.news_provider = MagicMock()
        orch.news_provider.get_headlines.return_value = {"brasil": [], "mundo": []}
        orch._headline_offer_counts = {}
        return orch

    def test_passes_saved_memories_into_prompt_context(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.memory_manager.get_memories.return_value = {"cor_favorita": "azul"}
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "oi", "animation": "TALKING", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._trigger_spontaneous_comment()

        orch.context_manager.build_prompt_context.assert_called_once_with(
            {"cor_favorita": "azul"}, SPONTANEOUS_TALK_PROMPT
        )

    def test_appends_news_context_to_prompt_when_available(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.news_provider.get_headlines.return_value = {"brasil": ["Manchete BR"], "mundo": []}
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "oi", "animation": "TALKING", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._trigger_spontaneous_comment()

        sent_prompt = orch.ai_provider.chat.call_args[0][0]
        assert "Manchete BR" in sent_prompt
        assert "[DESTAQUE]" in sent_prompt

    def test_does_not_append_news_block_when_no_headlines(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "oi", "animation": "TALKING", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._trigger_spontaneous_comment()

        sent_prompt = orch.ai_provider.chat.call_args[0][0]
        assert "Notícias recentes" not in sent_prompt

    def test_emits_speech_when_ai_has_something_to_say(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "Nossa, você já tá nesse jogo faz tempo, hein?",
            "animation": "TALKING", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        received = _capture(orch.event_bus, "SPONTANEOUS_SPEECH")
        orch._trigger_spontaneous_comment()

        assert len(received) == 1
        assert "jogo" in received[0]["speech"]
        orch.state_manager.set_state.assert_any_call("TALKING", reason="Spontaneous comment")

    def test_records_spontaneous_speech_into_conversation_history(self, monkeypatch):
        """Regression: spontaneous remarks used to never enter conversation
        history, so if the user later asked to hear more about something Silva
        brought up on its own, the AI had no memory of having said it."""
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "Vi uma notícia interessante hoje.",
            "animation": "TALKING", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._trigger_spontaneous_comment()

        orch.memory_manager.record_turn.assert_called_once_with("", "Vi uma notícia interessante hoje.")

    def test_does_not_record_history_when_ai_has_nothing_to_say(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "", "animation": "IDLE", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._trigger_spontaneous_comment()

        orch.memory_manager.record_turn.assert_not_called()

    def test_emits_nothing_when_ai_has_nothing_to_say(self, monkeypatch):
        """The prompt explicitly allows an empty speech when nothing's worth
        saying — spontaneous comments should never be forced."""
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "", "animation": "IDLE", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        received = _capture(orch.event_bus, "SPONTANEOUS_SPEECH")
        orch._trigger_spontaneous_comment()

        assert received == []

    def test_error_does_not_propagate(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.side_effect = RuntimeError("network down")
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._trigger_spontaneous_comment()  # should not raise


class TestAnnounceTaskOutcome:
    def _bare_orchestrator(self):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.event_bus = EventBus()
        orch.memory_manager = MagicMock()
        orch.memory_manager.get_history.return_value = []
        orch.context_manager = MagicMock()
        orch.context_manager.build_prompt_context.return_value = "prompt"
        orch.ai_provider = MagicMock()
        orch.state_manager = MagicMock()
        orch.tts = MagicMock()
        orch.settings = FakeSettings()
        return orch

    def test_on_task_completed_announces_the_result(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "Terminei a pesquisa, olha só o que achei!",
            "animation": "EXCITED", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        received = _capture(orch.event_bus, "SPONTANEOUS_SPEECH")

        orch._on_task_completed(
            task_id="t1", task_type="research", description="novidades do minecraft", result="resumo aqui"
        )

        assert received == [{"speech": "Terminei a pesquisa, olha só o que achei!"}]
        sent_instruction = orch.context_manager.build_prompt_context.call_args[0][1]
        assert "novidades do minecraft" in sent_instruction
        assert "resumo aqui" in sent_instruction

    def test_on_task_failed_announces_the_failure(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "Não consegui terminar essa pesquisa.",
            "animation": "CONFUSED", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        received = _capture(orch.event_bus, "SPONTANEOUS_SPEECH")

        orch._on_task_failed(
            task_id="t1", task_type="research", description="novidades do minecraft", error="network down"
        )

        assert received == [{"speech": "Não consegui terminar essa pesquisa."}]
        sent_instruction = orch.context_manager.build_prompt_context.call_args[0][1]
        assert "network down" in sent_instruction

    def test_records_announcement_into_history(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "Terminei!", "animation": "EXCITED", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._on_task_completed(task_id="t1", task_type="research", description="x", result="y")

        orch.memory_manager.record_turn.assert_called_once_with("", "Terminei!")

    def test_empty_speech_announces_nothing(self, monkeypatch):
        import threading
        import json
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.return_value = json.dumps({
            "speech": "", "animation": "IDLE", "action": "Nenhuma", "action_param": ""
        })
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        received = _capture(orch.event_bus, "SPONTANEOUS_SPEECH")

        orch._on_task_completed(task_id="t1", task_type="research", description="x", result="y")

        assert received == []
        orch.memory_manager.record_turn.assert_not_called()

    def test_error_does_not_propagate(self, monkeypatch):
        import threading
        orch = self._bare_orchestrator()
        orch.ai_provider.chat.side_effect = RuntimeError("boom")
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        orch._on_task_completed(task_id="t1", task_type="research", description="x", result="y")  # should not raise


class TestNerdModeAffectsSpontaneousTiming:
    def _bare_orchestrator(self, **overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.spontaneous_talk_enabled = True
        orch.nerd_mode_enabled = overrides.pop("nerd_mode_enabled", False)
        orch.state_machine = MagicMock()
        orch.state_machine.get_state.return_value = "IDLE"
        orch._last_interaction_time = overrides.pop("last_interaction_time", time.monotonic())
        orch._last_spontaneous_time = overrides.pop("last_spontaneous_time", time.monotonic())
        orch._trigger_spontaneous_comment = MagicMock()
        return orch

    def test_normal_mode_waits_the_longer_idle_gap(self):
        """Just past the NERD idle gap but still under the normal one —
        should NOT trigger when nerd mode is off."""
        orch = self._bare_orchestrator(
            nerd_mode_enabled=False,
            last_interaction_time=time.monotonic() - (NERD_SPONTANEOUS_TALK_IDLE_GAP_S + 1),
            last_spontaneous_time=time.monotonic() - (NERD_SPONTANEOUS_TALK_CHECK_INTERVAL_S + 1),
        )
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_not_called()

    def test_nerd_mode_triggers_at_the_shorter_idle_gap(self):
        """Same elapsed time as above, but with nerd mode on — the shorter
        thresholds should be satisfied."""
        orch = self._bare_orchestrator(
            nerd_mode_enabled=True,
            last_interaction_time=time.monotonic() - (NERD_SPONTANEOUS_TALK_IDLE_GAP_S + 1),
            last_spontaneous_time=time.monotonic() - (NERD_SPONTANEOUS_TALK_CHECK_INTERVAL_S + 1),
        )
        orch._maybe_speak_spontaneously()
        orch._trigger_spontaneous_comment.assert_called_once()
