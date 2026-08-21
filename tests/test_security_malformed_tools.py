"""FASE 15 — ferramentas malformadas.

A tool's dispatch handler (today's built-ins, or anything registered in the
future) must never be able to take AgentCore.execute() down with it — a bug
in one tool shouldn't corrupt the event bookkeeping (ACTION_EXECUTED/
ACTION_REJECTED) or propagate an exception out of execute() itself. The
orchestrator's worker thread has its own catch-all too (defense in depth),
but that shouldn't be the only thing standing between a bad tool and a dead
thread."""

from unittest.mock import MagicMock

from src.core.agent_core import AgentCore
from src.core.event_bus import EventBus
from src.core.tool_registry import PermissionTier, ToolRegistry, ToolSpec


def _capture(event_bus, event_type):
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


def _agent_with_tool(tier, dispatch):
    registry = ToolRegistry()
    registry.register(ToolSpec(name="flaky_tool", tier=tier, description="test-only", dispatch=dispatch))
    event_bus = EventBus()
    return AgentCore(registry, event_bus), event_bus


class TestDispatchExceptionIsContained:
    def test_raising_safe_tool_does_not_propagate(self):
        agent, _ = _agent_with_tool(PermissionTier.SAFE, dispatch=lambda p: (_ for _ in ()).throw(RuntimeError("boom")))

        result = agent.execute("flaky_tool", "param")  # must not raise

        assert result is False

    def test_raising_tool_emits_action_rejected_not_executed(self):
        agent, event_bus = _agent_with_tool(PermissionTier.SAFE, dispatch=lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
        executed = _capture(event_bus, "ACTION_EXECUTED")
        rejected = _capture(event_bus, "ACTION_REJECTED")

        agent.execute("flaky_tool", "param")

        assert executed == []
        assert len(rejected) == 1

    def test_raising_confirm_tool_still_contained_after_approval(self):
        confirm_fn = MagicMock()
        from src.desktop.permission_policy import PolicyDecision
        confirm_fn.return_value = PolicyDecision.ONCE
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="flaky_confirm_tool", tier=PermissionTier.CONFIRM, description="test-only",
            dispatch=lambda p: (_ for _ in ()).throw(TypeError("unexpected shape")),
        ))
        event_bus = EventBus()
        agent = AgentCore(registry, event_bus, confirm_fn=confirm_fn)

        result = agent.execute("flaky_confirm_tool", {"weird": "shape"})  # must not raise

        assert result is False

    def test_next_call_after_a_crash_still_works_normally(self):
        """A crashing tool must not corrupt AgentCore's own state for
        subsequent, unrelated calls."""
        calls = []

        def _dispatch(param):
            if param == "crash":
                raise RuntimeError("boom")
            calls.append(param)
            return True

        agent, _ = _agent_with_tool(PermissionTier.SAFE, dispatch=_dispatch)

        first = agent.execute("flaky_tool", "crash")
        second = agent.execute("flaky_tool", "fine")

        assert first is False
        assert second is True
        assert calls == ["fine"]
