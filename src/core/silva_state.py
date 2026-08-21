import time


class SilvaState:
    """Answers "what's Silva's current context?" from one place, instead of
    a caller reaching into window_manager, voice_input, policy_manager,
    background_task_manager, memory_manager, and settings separately (see
    FASE 0 audit / FASE 4 plan).

    Deliberately NOT a second store of mutable state — every field in
    snapshot() is computed fresh, at call time, from each subsystem's own
    already-authoritative data. That's the point: a SilvaState that owned its
    own copy of "current window" or "is listening" would just be one more
    place those facts could drift out of sync with the real thing and one
    more object needing its own locking. This is a read-only query facade
    over data other modules already own and already keep correct.

    Only exposes fields backed by something the codebase can actually answer
    today. voice.speaking landed with FASE 14 (barge-in — see
    CompanionOrchestrator._is_speaking). Some fields the FASE 4 spec sketches
    (conversation.current_topic, vision.last_capture) still have no real
    signal to read yet — no topic tracker, no capture timestamp — so they're
    left out rather than faked. Add them here once the phase that actually
    produces that data lands, not before."""

    def __init__(self, orchestrator):
        self._orch = orchestrator

    def snapshot(self) -> dict:
        return {
            "desktop": self._desktop(),
            "vision": self._vision(),
            "voice": self._voice(),
            "permissions": self._permissions(),
            "tasks": self._tasks(),
            "memory": self._memory(),
            "behavior": self._behavior(),
        }

    def _desktop(self) -> dict:
        orch = self._orch
        return {
            "active_window": orch._last_window_title,
            "category": orch._last_app_category,
            "is_game": orch._is_game_active,
            "idle_seconds": time.monotonic() - orch._last_interaction_time,
        }

    def _vision(self) -> dict:
        orch = self._orch
        settings = orch.settings
        result = {
            "monitoring_enabled": settings.get("screen_monitoring_enabled", False),
            "private_mode": settings.get("private_mode", True),
        }
        compute_mode = getattr(orch, "_compute_vision_mode", None)
        if compute_mode is not None:
            result["mode"] = compute_mode().value
        translation_mode = getattr(orch, "translation_mode", None)
        if translation_mode is not None:
            result["translation_mode_state"] = translation_mode.state.value
        return result

    def _voice(self) -> dict:
        orch = self._orch
        return {
            "listening": bool(getattr(orch.voice_input, "is_listening", False)),
            "hands_free_enabled": bool(getattr(orch.voice_input, "hands_free_enabled", False)),
            "system_audio_listening": bool(getattr(orch.system_audio_listener, "enabled", False)),
            # FASE 14 (barge-in) — previously listed in this class's own
            # docstring as a gap with "no real signal to read yet"; now
            # there is one (CompanionOrchestrator._is_speaking).
            "speaking": bool(getattr(orch, "_is_speaking", False)),
        }

    def _permissions(self) -> dict:
        policy_manager = getattr(self._orch, "policy_manager", None)
        if policy_manager is None:
            return {"active": {}}
        return {"active": policy_manager.all_policies()}

    def _tasks(self) -> dict:
        manager = getattr(self._orch, "background_task_manager", None)
        if manager is None:
            running, running_count = [], 0
        else:
            running = [t for t in manager.list_tasks() if t["status"] in ("PENDING", "RUNNING")]
            running_count = len(running)
        scheduler = getattr(self._orch, "scheduler", None)
        pending_reminders = scheduler.list_pending() if scheduler is not None else []
        task_manager = getattr(self._orch, "task_manager", None)
        if task_manager is None:
            agent_tasks_active_count = 0
        else:
            agent_tasks_active_count = sum(
                1 for t in task_manager.list_tasks() if t.status in ("PENDING", "RUNNING", "PAUSED")
            )
        return {
            "running": running, "running_count": running_count,
            "pending_reminders_count": len(pending_reminders),
            "agent_tasks_active_count": agent_tasks_active_count,
        }

    def _memory(self) -> dict:
        memories = self._orch.memory_manager.get_memories()
        return {"saved_keys": sorted(memories.keys()), "saved_count": len(memories)}

    def _behavior(self) -> dict:
        orch = self._orch
        return {
            "nerd_mode_enabled": bool(orch.nerd_mode_enabled),
            "spontaneous_talk_enabled": bool(orch.spontaneous_talk_enabled),
        }
