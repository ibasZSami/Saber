from unittest.mock import MagicMock

from src.core.agent_core import AgentCore
from src.core.event_bus import EventBus
from src.core.tool_registry import build_default_registry
from src.desktop.permission_policy import PermissionPolicyManager, PolicyDecision


def _capture(event_bus, event_type):
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


def _agent_core(confirm_fn=None, policy_manager=None):
    action_manager = MagicMock()
    memory_manager = MagicMock()
    registry = build_default_registry(action_manager, memory_manager)
    event_bus = EventBus()
    return (
        AgentCore(registry, event_bus, confirm_fn=confirm_fn, policy_manager=policy_manager),
        action_manager,
        memory_manager,
    )


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


class TestAgentCoreRealConfirmation:
    """FASE 1: when a real confirm_fn is wired, CONFIRM tools must ask BEFORE
    running — not execute-then-flag like the confirm_fn=None fallback above.
    confirm_fn returns a PolicyDecision (FASE 2), not a bare bool — ONCE/
    SESSION/ALWAYS all approve running once; only DECLINED/BLOCKED deny."""

    def test_approved_confirm_action_executes(self):
        approvals = []

        def confirm_fn(action, param, description):
            approvals.append((action, param, description))
            return PolicyDecision.ONCE

        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn)
        action_manager.open_application.return_value = True

        handled = agent.execute("open_application", "chrome")

        assert handled is True
        action_manager.open_application.assert_called_once_with("chrome")
        assert approvals == [("open_application", "chrome", 'Silva quer abrir o aplicativo "chrome".')]

    def test_denied_confirm_action_never_dispatches(self):
        agent, action_manager, _ = _agent_core(confirm_fn=lambda action, param, description: PolicyDecision.DECLINED)

        handled = agent.execute("open_application", "chrome")

        assert handled is False
        action_manager.open_application.assert_not_called()

    def test_denial_emits_permission_denied_and_action_rejected_not_executed(self):
        agent, action_manager, _ = _agent_core(confirm_fn=lambda action, param, description: PolicyDecision.DECLINED)
        requested = _capture(agent.event_bus, "PERMISSION_REQUESTED")
        denied = _capture(agent.event_bus, "PERMISSION_DENIED")
        rejected = _capture(agent.event_bus, "ACTION_REJECTED")
        executed = _capture(agent.event_bus, "ACTION_EXECUTED")
        auto_approved = _capture(agent.event_bus, "ACTION_CONFIRM_AUTO_APPROVED")

        agent.execute("open_application", "chrome")

        assert len(requested) == 1 and requested[0]["action"] == "open_application"
        assert denied == [{"action": "open_application", "action_param": "chrome"}]
        assert len(rejected) == 1
        assert executed == []
        assert auto_approved == []  # a real confirm_fn is wired — never the legacy fallback event

    def test_approval_emits_permission_granted_then_executed(self):
        agent, action_manager, _ = _agent_core(confirm_fn=lambda action, param, description: PolicyDecision.ONCE)
        action_manager.open_application.return_value = True
        granted = _capture(agent.event_bus, "PERMISSION_GRANTED")
        executed = _capture(agent.event_bus, "ACTION_EXECUTED")

        agent.execute("open_application", "chrome")

        assert granted == [{"action": "open_application", "action_param": "chrome"}]
        assert len(executed) == 1

    def test_safe_tier_never_calls_confirm_fn(self):
        confirm_fn = MagicMock(return_value=PolicyDecision.ONCE)
        agent, _, memory_manager = _agent_core(confirm_fn=confirm_fn)

        agent.execute("remember", {"key": "cor_favorita", "value": "roxo"})

        confirm_fn.assert_not_called()

    def test_dangerous_tier_still_rejected_without_calling_confirm_fn(self):
        """DANGEROUS has no tool using it yet, but the tier itself must stay
        fail-closed even with a confirm_fn wired — it is not a CONFIRM tool."""
        from src.core.tool_registry import ToolSpec, PermissionTier

        confirm_fn = MagicMock(return_value=PolicyDecision.ONCE)
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn)
        agent.registry.register(ToolSpec(
            name="format_disk", tier=PermissionTier.DANGEROUS,
            description="test-only", dispatch=lambda p: True,
        ))

        handled = agent.execute("format_disk", None)

        assert handled is False
        confirm_fn.assert_not_called()


class TestAgentCorePolicyManager:
    """FASE 2: once/session/always/blocked — a policy_manager lets a
    previous decision skip the dialog entirely (granted or blocked), and
    ONCE/DECLINED never get remembered."""

    def test_blocked_target_denies_without_calling_confirm_fn(self):
        policy = PermissionPolicyManager()
        policy.set_policy("open_application", "chrome", PolicyDecision.BLOCKED)
        confirm_fn = MagicMock()
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)

        handled = agent.execute("open_application", "chrome")

        assert handled is False
        confirm_fn.assert_not_called()
        action_manager.open_application.assert_not_called()

    def test_blocked_target_emits_permission_denied(self):
        policy = PermissionPolicyManager()
        policy.set_policy("open_application", "chrome", PolicyDecision.BLOCKED)
        agent, _, _ = _agent_core(confirm_fn=MagicMock(), policy_manager=policy)
        denied = _capture(agent.event_bus, "PERMISSION_DENIED")
        requested = _capture(agent.event_bus, "PERMISSION_REQUESTED")

        agent.execute("open_application", "chrome")

        assert len(denied) == 1
        assert requested == []  # blocked short-circuits before ever asking

    def test_always_granted_target_executes_without_calling_confirm_fn(self):
        policy = PermissionPolicyManager()
        policy.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)
        confirm_fn = MagicMock()
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)
        action_manager.open_application.return_value = True

        handled = agent.execute("open_application", "chrome")

        assert handled is True
        confirm_fn.assert_not_called()
        action_manager.open_application.assert_called_once_with("chrome")

    def test_choosing_always_persists_and_skips_the_dialog_next_time(self):
        policy = PermissionPolicyManager()
        confirm_fn = MagicMock(return_value=PolicyDecision.ALWAYS)
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)
        action_manager.open_application.return_value = True

        agent.execute("open_application", "chrome")  # asks, user picks "sempre"
        agent.execute("open_application", "chrome")  # must not ask again

        assert confirm_fn.call_count == 1
        assert action_manager.open_application.call_count == 2

    def test_choosing_session_persists_for_this_run_only(self):
        policy = PermissionPolicyManager()
        confirm_fn = MagicMock(return_value=PolicyDecision.SESSION)
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)
        action_manager.open_application.return_value = True

        agent.execute("open_application", "chrome")
        agent.execute("open_application", "chrome")

        assert confirm_fn.call_count == 1  # second call reused the session grant
        assert policy.get_policy("open_application", "chrome") == PolicyDecision.SESSION

    def test_choosing_once_asks_again_next_time(self):
        policy = PermissionPolicyManager()
        confirm_fn = MagicMock(return_value=PolicyDecision.ONCE)
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)
        action_manager.open_application.return_value = True

        agent.execute("open_application", "chrome")
        agent.execute("open_application", "chrome")

        assert confirm_fn.call_count == 2  # "once" is never remembered

    def test_declined_is_never_persisted(self):
        policy = PermissionPolicyManager()
        confirm_fn = MagicMock(return_value=PolicyDecision.DECLINED)
        agent, _, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)

        agent.execute("open_application", "chrome")

        assert policy.get_policy("open_application", "chrome") is None

    def test_revoke_makes_it_ask_again(self):
        policy = PermissionPolicyManager()
        policy.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)
        confirm_fn = MagicMock(return_value=PolicyDecision.ONCE)
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)
        action_manager.open_application.return_value = True

        policy.revoke("open_application", "chrome")
        agent.execute("open_application", "chrome")

        confirm_fn.assert_called_once()

    def test_policy_target_uses_application_key_for_dict_params(self):
        """set_app_volume's action_param is a dict — the policy must key on
        the app name inside it, not the whole dict/None."""
        policy = PermissionPolicyManager()
        policy.set_policy("set_app_volume", "spotify", PolicyDecision.BLOCKED)
        confirm_fn = MagicMock()
        agent, _, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)

        handled = agent.execute("set_app_volume", {"application": "spotify", "level": 50})

        assert handled is False
        confirm_fn.assert_not_called()

    def test_policy_target_is_case_insensitive(self):
        policy = PermissionPolicyManager()
        policy.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)
        confirm_fn = MagicMock()
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=policy)
        action_manager.open_application.return_value = True

        handled = agent.execute("open_application", "  Chrome  ")

        assert handled is True
        confirm_fn.assert_not_called()

    def test_without_policy_manager_behaves_like_fase_1_always_asking(self):
        confirm_fn = MagicMock(return_value=PolicyDecision.ALWAYS)
        agent, action_manager, _ = _agent_core(confirm_fn=confirm_fn, policy_manager=None)
        action_manager.open_application.return_value = True

        agent.execute("open_application", "chrome")
        agent.execute("open_application", "chrome")

        assert confirm_fn.call_count == 2  # nothing to remember without a policy_manager
