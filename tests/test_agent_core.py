from unittest.mock import MagicMock

from src.core.agent_core import AgentCore
from src.core.event_bus import EventBus
from src.core.tool_registry import build_default_registry


def _capture(event_bus, event_type):
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


def _agent_core():
    action_manager = MagicMock()
    memory_manager = MagicMock()
    registry = build_default_registry(action_manager, memory_manager)
    event_bus = EventBus()
    return AgentCore(registry, event_bus), action_manager, memory_manager


class TestAgentCoreExecute:
    """Reproduces the exact behavioral matrix CompanionOrchestrator._execute_action
    used to guarantee directly, before it delegated here — see FASE 2 plan."""

    def test_open_application(self):
        agent, action_manager, _ = _agent_core()
        action_manager.open_application.return_value = True

        handled = agent.execute("open_application", "chrome")

        action_manager.open_application.assert_called_once_with("chrome")
        assert handled is True

    def test_open_url(self):
        agent, action_manager, _ = _agent_core()
        action_manager.open_url.return_value = True

        agent.execute("open_url", "https://example.com")

        action_manager.open_url.assert_called_once_with("https://example.com")

    def test_search_web(self):
        agent, action_manager, _ = _agent_core()
        action_manager.search_web.return_value = True

        agent.execute("search_web", "python")

        action_manager.search_web.assert_called_once_with("python")

    def test_remember_with_valid_dict(self):
        agent, _, memory_manager = _agent_core()

        agent.execute("remember", {"key": "cor_favorita", "value": "roxo"})

        memory_manager.remember.assert_called_once_with("cor_favorita", "roxo")

    def test_remember_without_key_is_ignored(self):
        agent, _, memory_manager = _agent_core()

        handled = agent.execute("remember", {"value": "roxo"})

        memory_manager.remember.assert_not_called()
        assert handled is False

    def test_forget_memory_with_dict_param(self):
        agent, _, memory_manager = _agent_core()

        agent.execute("forget_memory", {"key": "cor_favorita"})

        memory_manager.forget.assert_called_once_with("cor_favorita")

    def test_forget_memory_with_plain_string_param(self):
        agent, _, memory_manager = _agent_core()

        agent.execute("forget_memory", "cor_favorita")

        memory_manager.forget.assert_called_once_with("cor_favorita")

    def test_no_action_does_nothing(self):
        agent, action_manager, memory_manager = _agent_core()

        handled = agent.execute("Nenhuma", "")

        action_manager.open_application.assert_not_called()
        memory_manager.remember.assert_not_called()
        memory_manager.forget.assert_not_called()
        assert handled is False

    def test_unknown_action_is_ignored_safely(self):
        agent, _, _ = _agent_core()
        assert agent.execute("fly_to_moon", "now") is False

    def test_action_without_param_is_ignored(self):
        agent, action_manager, _ = _agent_core()

        agent.execute("open_application", "")

        action_manager.open_application.assert_not_called()


class TestAgentCoreEvents:
    def test_successful_action_emits_requested_then_executed(self):
        agent, action_manager, _ = _agent_core()
        action_manager.open_application.return_value = True
        requested = _capture(agent.event_bus, "ACTION_REQUESTED")
        executed = _capture(agent.event_bus, "ACTION_EXECUTED")
        rejected = _capture(agent.event_bus, "ACTION_REJECTED")

        agent.execute("open_application", "chrome")

        assert requested == [{"action": "open_application", "action_param": "chrome"}]
        assert executed == [{"action": "open_application", "action_param": "chrome"}]
        assert rejected == []

    def test_failed_action_emits_rejected_not_executed(self):
        agent, action_manager, _ = _agent_core()
        action_manager.open_application.return_value = False
        executed = _capture(agent.event_bus, "ACTION_EXECUTED")
        rejected = _capture(agent.event_bus, "ACTION_REJECTED")

        handled = agent.execute("open_application", "not_allowed_app")

        assert handled is False
        assert executed == []
        assert len(rejected) == 1

    def test_no_action_emits_nothing(self):
        agent, _, _ = _agent_core()
        requested = _capture(agent.event_bus, "ACTION_REQUESTED")

        agent.execute("Nenhuma", "")

        assert requested == []

    def test_confirm_tier_auto_approves_and_emits_flag_event(self):
        """open_application/open_url are CONFIRM-tier — no confirmation UI exists
        yet, so they still execute, but a distinct event marks that this happened
        without a real prompt (see FASE 2 plan's CONFIRM interim-behavior call)."""
        agent, action_manager, _ = _agent_core()
        action_manager.open_url.return_value = True
        auto_approved = _capture(agent.event_bus, "ACTION_CONFIRM_AUTO_APPROVED")

        handled = agent.execute("open_url", "https://example.com")

        assert handled is True
        assert auto_approved == [{"action": "open_url", "action_param": "https://example.com"}]

    def test_safe_tier_does_not_emit_confirm_auto_approved(self):
        agent, _, memory_manager = _agent_core()
        auto_approved = _capture(agent.event_bus, "ACTION_CONFIRM_AUTO_APPROVED")

        agent.execute("remember", {"key": "cor_favorita", "value": "roxo"})

        assert auto_approved == []
