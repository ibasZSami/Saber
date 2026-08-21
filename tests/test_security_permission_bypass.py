"""FASE 15 — bypass de permissão.

These tests don't re-test what test_agent_core.py's TestAgentCorePolicyManager
already covers in depth (grant/block/session/always flows) — they audit the
one thing a future change could silently break: that every tool touching the
real system is tagged at the tier the rest of AgentCore's logic assumes."""

from unittest.mock import MagicMock

from src.core.tool_registry import PermissionTier, build_default_registry

# Tools with zero real-world side effects on the system — reading memory,
# opening a browser tab (a URL the user/AI chose, not arbitrary code), and
# kicking off a read-only background search. Everything else that can affect
# a running process, launch software, or touch OS audio state must NOT be SAFE.
_EXPECTED_SAFE_TOOLS = {"observe_screen", "translate_screen", "search_web", "remember", "forget_memory", "research_topic"}


class TestPermissionTierAudit:
    """Regression guard: a future tool accidentally registered at the wrong
    tier (or an existing one downgraded) would silently skip the real
    confirmation flow built in FASE 1/2 — this fails loudly instead."""

    def _registry(self):
        return build_default_registry(MagicMock(), MagicMock())

    def test_every_tool_that_can_affect_the_system_is_not_safe(self):
        registry = self._registry()
        for name in ("open_application", "close_application", "open_url", "set_app_volume"):
            tier = registry.tier_of(name)
            assert tier != PermissionTier.SAFE, f"{name} must not be SAFE-tier"

    def test_expected_safe_tools_are_exactly_safe(self):
        registry = self._registry()
        for name in _EXPECTED_SAFE_TOOLS:
            assert registry.tier_of(name) == PermissionTier.SAFE, f"{name} should be SAFE-tier"

    def test_no_tool_is_silently_untagged(self):
        """Every tool the AI is told about must have a real tier — an
        unregistered/None tier would fall through AgentCore's tier checks
        into whatever the default execute() path does, which is not a
        deliberate decision for any tool."""
        registry = self._registry()
        for name in _EXPECTED_SAFE_TOOLS | {"open_application", "close_application", "open_url", "set_app_volume"}:
            assert registry.tier_of(name) is not None


class TestDangerousTierNeverExecutesRegardlessOfConfirmFn:
    """DANGEROUS is reserved (no tool uses it yet, per README), but the tier
    itself must fail closed unconditionally — see FASE 1's design note: it's
    the one tier with no confirmation UI at all, on purpose."""

    def test_dangerous_tool_rejected_even_when_confirm_fn_always_approves(self):
        from src.core.agent_core import AgentCore
        from src.core.event_bus import EventBus
        from src.core.tool_registry import ToolRegistry, ToolSpec
        from src.desktop.permission_policy import PolicyDecision

        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="format_disk", tier=PermissionTier.DANGEROUS, description="test-only",
            dispatch=lambda p: True,
        ))
        confirm_fn = MagicMock(return_value=PolicyDecision.ALWAYS)
        agent = AgentCore(registry, EventBus(), confirm_fn=confirm_fn)

        result = agent.execute("format_disk", None)

        assert result is False
        confirm_fn.assert_not_called()

    def test_dangerous_tool_rejected_even_with_a_granting_policy_manager(self):
        """A BLOCKED/ALWAYS policy is keyed by (action, target) for CONFIRM
        tools — even if one somehow existed for a DANGEROUS-tier action name,
        the tier check must still short-circuit before policy lookup."""
        from src.core.agent_core import AgentCore
        from src.core.event_bus import EventBus
        from src.core.tool_registry import ToolRegistry, ToolSpec
        from src.desktop.permission_policy import PermissionPolicyManager, PolicyDecision

        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="format_disk", tier=PermissionTier.DANGEROUS, description="test-only",
            dispatch=lambda p: True,
        ))
        policy_manager = PermissionPolicyManager()
        policy_manager.set_policy("format_disk", "c_drive", PolicyDecision.ALWAYS)
        agent = AgentCore(registry, EventBus(), policy_manager=policy_manager)

        result = agent.execute("format_disk", "c_drive")

        assert result is False


class TestCloseApplicationOnlyAffectsAllowlistedApps:
    """Reproduces src/desktop/actions.py's own invariant at the dispatch
    boundary — close_application must never reach psutil.terminate() for an
    app that was never explicitly allowlisted, regardless of what the AI
    passes as action_param."""

    def test_close_application_dispatch_rejects_non_allowlisted_app(self):
        from src.desktop.actions import DesktopActionManager
        from src.desktop.permissions import PermissionManager

        permission_manager = PermissionManager({"notepad": "notepad.exe"})
        action_manager = DesktopActionManager(permission_manager)

        result = action_manager.close_application("some_random_process_never_configured")

        assert result is False
