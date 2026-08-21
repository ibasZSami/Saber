from unittest.mock import MagicMock

from src.core.silva_state import SilvaState


class _FakeOrchestrator:
    """Plain stand-in exposing exactly the attributes SilvaState reads —
    mirrors the CompanionOrchestrator.__new__(...) bare-construction pattern
    already used throughout tests/test_orchestrator_actions.py, since
    SilvaState is meant to be trivially testable without a real orchestrator."""

    def __init__(self, **overrides):
        self._last_window_title = "Visual Studio Code"
        self._last_app_category = "coding"
        self._is_game_active = False
        self._last_interaction_time = 0.0

        self.settings = MagicMock()
        self.settings.get.side_effect = lambda key, default=None: {
            "screen_monitoring_enabled": False,
            "private_mode": True,
        }.get(key, default)

        self.voice_input = MagicMock()
        self.voice_input.is_listening = False
        self.voice_input.hands_free_enabled = False

        self.system_audio_listener = MagicMock()
        self.system_audio_listener.enabled = False

        self.policy_manager = MagicMock()
        self.policy_manager.all_policies.return_value = {}

        self.background_task_manager = MagicMock()
        self.background_task_manager.list_tasks.return_value = []

        self.scheduler = MagicMock()
        self.scheduler.list_pending.return_value = []

        self.memory_manager = MagicMock()
        self.memory_manager.get_memories.return_value = {}

        self.nerd_mode_enabled = False
        self.spontaneous_talk_enabled = True

        for key, value in overrides.items():
            setattr(self, key, value)


class TestSnapshotShape:
    def test_snapshot_has_every_top_level_section(self):
        state = SilvaState(_FakeOrchestrator())
        snapshot = state.snapshot()
        assert set(snapshot.keys()) == {"desktop", "vision", "voice", "permissions", "tasks", "memory", "behavior"}

    def test_snapshot_is_computed_fresh_not_cached(self):
        """Two snapshots taken after underlying state changes must differ —
        SilvaState must never memoize a stale value."""
        orch = _FakeOrchestrator()
        state = SilvaState(orch)

        before = state.snapshot()
        orch.nerd_mode_enabled = True
        after = state.snapshot()

        assert before["behavior"]["nerd_mode_enabled"] is False
        assert after["behavior"]["nerd_mode_enabled"] is True


class TestDesktopSection:
    def test_reflects_last_known_window_and_category(self):
        orch = _FakeOrchestrator(_last_window_title="Chrome", _last_app_category="browsing")
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["desktop"]["active_window"] == "Chrome"
        assert snapshot["desktop"]["category"] == "browsing"

    def test_reflects_game_flag(self):
        orch = _FakeOrchestrator(_is_game_active=True)
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["desktop"]["is_game"] is True

    def test_idle_seconds_grows_with_time_since_last_interaction(self):
        import time
        orch = _FakeOrchestrator(_last_interaction_time=time.monotonic() - 5)
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["desktop"]["idle_seconds"] >= 5


class TestVisionSection:
    def test_reflects_monitoring_and_private_mode_settings(self):
        orch = _FakeOrchestrator()
        orch.settings.get.side_effect = lambda key, default=None: {
            "screen_monitoring_enabled": True,
            "private_mode": False,
        }.get(key, default)

        snapshot = SilvaState(orch).snapshot()

        assert snapshot["vision"]["monitoring_enabled"] is True
        assert snapshot["vision"]["private_mode"] is False

    def test_omits_mode_when_orchestrator_has_no_compute_vision_mode(self):
        """_FakeOrchestrator has no _compute_vision_mode (unlike the real
        CompanionOrchestrator) — must degrade gracefully, not raise."""
        orch = _FakeOrchestrator()
        snapshot = SilvaState(orch).snapshot()
        assert "mode" not in snapshot["vision"]

    def test_includes_mode_when_orchestrator_provides_it(self):
        from src.vision.continuous_vision import VisionMode
        orch = _FakeOrchestrator()
        orch._compute_vision_mode = lambda: VisionMode.ACTIVE
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["vision"]["mode"] == "ACTIVE"

    def test_omits_translation_mode_state_without_a_translation_mode(self):
        orch = _FakeOrchestrator()
        snapshot = SilvaState(orch).snapshot()
        assert "translation_mode_state" not in snapshot["vision"]

    def test_includes_translation_mode_state_when_present(self):
        from src.core.translation_mode import TranslationModeState
        orch = _FakeOrchestrator()
        orch.translation_mode = MagicMock()
        orch.translation_mode.state = TranslationModeState.RUNNING
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["vision"]["translation_mode_state"] == "RUNNING"


class TestVoiceSection:
    def test_reflects_mic_listening_state(self):
        orch = _FakeOrchestrator()
        orch.voice_input.is_listening = True
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["voice"]["listening"] is True

    def test_reflects_hands_free_state(self):
        orch = _FakeOrchestrator()
        orch.voice_input.hands_free_enabled = True
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["voice"]["hands_free_enabled"] is True

    def test_reflects_system_audio_listening_state(self):
        orch = _FakeOrchestrator()
        orch.system_audio_listener.enabled = True
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["voice"]["system_audio_listening"] is True

    def test_missing_attributes_default_to_false_not_an_exception(self):
        """A voice_input/system_audio_listener stand-in that doesn't define
        these attributes (e.g. a bare MagicMock in some other test's setup)
        must not crash snapshot() — this is a read facade, it should degrade
        gracefully, not become a new source of AttributeErrors."""
        orch = _FakeOrchestrator()
        orch.voice_input = object()  # no is_listening/hands_free_enabled at all
        orch.system_audio_listener = object()

        snapshot = SilvaState(orch).snapshot()

        assert snapshot["voice"] == {"listening": False, "hands_free_enabled": False, "system_audio_listening": False}


class TestPermissionsSection:
    def test_reflects_policy_manager_snapshot(self):
        orch = _FakeOrchestrator()
        orch.policy_manager.all_policies.return_value = {"open_application:chrome": "always"}
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["permissions"]["active"] == {"open_application:chrome": "always"}

    def test_missing_policy_manager_yields_empty_not_an_exception(self):
        orch = _FakeOrchestrator(policy_manager=None)
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["permissions"]["active"] == {}


class TestTasksSection:
    def test_filters_to_only_pending_and_running_tasks(self):
        orch = _FakeOrchestrator()
        orch.background_task_manager.list_tasks.return_value = [
            {"id": "1", "status": "RUNNING"},
            {"id": "2", "status": "COMPLETED"},
            {"id": "3", "status": "PENDING"},
            {"id": "4", "status": "FAILED"},
        ]

        snapshot = SilvaState(orch).snapshot()

        running_ids = {t["id"] for t in snapshot["tasks"]["running"]}
        assert running_ids == {"1", "3"}
        assert snapshot["tasks"]["running_count"] == 2

    def test_missing_background_task_manager_yields_empty_not_an_exception(self):
        orch = _FakeOrchestrator(background_task_manager=None)
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["tasks"] == {
            "running": [], "running_count": 0, "pending_reminders_count": 0, "agent_tasks_active_count": 0,
        }

    def test_reflects_active_agent_tasks_count(self):
        from src.core.task_manager import TaskManager
        orch = _FakeOrchestrator()
        orch.task_manager = TaskManager(MagicMock())
        orch.task_manager.create_task("x")
        running = orch.task_manager.create_task("y")
        orch.task_manager.start(running.id)
        orch.task_manager.complete(running.id, "done")
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["tasks"]["agent_tasks_active_count"] == 1

    def test_missing_task_manager_yields_zero_not_an_exception(self):
        orch = _FakeOrchestrator(task_manager=None)
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["tasks"]["agent_tasks_active_count"] == 0

    def test_reflects_pending_reminders_count(self):
        orch = _FakeOrchestrator()
        orch.scheduler.list_pending.return_value = [MagicMock(), MagicMock()]
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["tasks"]["pending_reminders_count"] == 2

    def test_missing_scheduler_yields_zero_not_an_exception(self):
        orch = _FakeOrchestrator(scheduler=None)
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["tasks"]["pending_reminders_count"] == 0


class TestMemorySection:
    def test_reflects_saved_memory_keys_and_count(self):
        orch = _FakeOrchestrator()
        orch.memory_manager.get_memories.return_value = {"cor_favorita": "roxo", "jogo_favorito": "xadrez"}

        snapshot = SilvaState(orch).snapshot()

        assert snapshot["memory"]["saved_keys"] == ["cor_favorita", "jogo_favorito"]
        assert snapshot["memory"]["saved_count"] == 2


class TestBehaviorSection:
    def test_reflects_nerd_mode_and_spontaneous_talk_flags(self):
        orch = _FakeOrchestrator(nerd_mode_enabled=True, spontaneous_talk_enabled=False)
        snapshot = SilvaState(orch).snapshot()
        assert snapshot["behavior"] == {"nerd_mode_enabled": True, "spontaneous_talk_enabled": False}
