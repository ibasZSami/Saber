import time
from unittest.mock import MagicMock

from PySide6.QtCore import QTimer

from src.core.orchestrator import CompanionOrchestrator, SPONTANEOUS_TALK_PROMPT
from src.core.event_bus import EventBus


def _bare_orchestrator():
    """Builds an orchestrator without running __init__ (which needs sprites, AI keys, etc.),
    just to unit-test the action-dispatch logic in isolation."""
    orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
    orch.action_manager = MagicMock()
    orch.memory_manager = MagicMock()
    orch.event_bus = EventBus()
    return orch


def _capture(event_bus, event_type):
    """Subscribes a list to an EventBus topic and returns it; captured kwargs append live."""
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


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


class TestInitTtsProvider:
    def _bare_orchestrator(self, **settings_overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.settings = FakeSettings(**settings_overrides)
        return orch

    def test_defaults_to_edge_tts(self):
        from src.voice.tts import EdgeTTSProvider
        orch = self._bare_orchestrator()
        assert isinstance(orch._init_tts_provider(), EdgeTTSProvider)

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


class TestMaybeSpeakSpontaneously:
    def _bare_orchestrator(self, **overrides):
        orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
        orch.spontaneous_talk_enabled = overrides.pop("spontaneous_talk_enabled", True)
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
