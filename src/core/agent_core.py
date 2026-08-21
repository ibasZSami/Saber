import logging
from typing import Any, Callable, Optional, Tuple

from src.core.action_descriptions import describe_action
from src.core.event_bus import (
    EventBus,
    ACTION_REQUESTED,
    ACTION_EXECUTED,
    ACTION_REJECTED,
    ACTION_CONFIRM_AUTO_APPROVED,
    PERMISSION_REQUESTED,
    PERMISSION_GRANTED,
    PERMISSION_DENIED,
)
from src.core.tool_registry import PermissionTier, ToolRegistry
from src.desktop.permission_policy import PermissionPolicyManager, PolicyDecision, policy_target

ConfirmFn = Callable[[str, Any, str], PolicyDecision]

# Decisions that mean "run it" — everything else (BLOCKED, DECLINED) means don't.
_APPROVING_DECISIONS = (PolicyDecision.ONCE, PolicyDecision.SESSION, PolicyDecision.ALWAYS)


class AgentCore:
    """Owns tool dispatch: turns a parsed (action, action_param) into a real
    side effect through the ToolRegistry, enforcing permission tiers first.
    Deliberately does NOT own AI calls, memory history, TTS, or vision — those
    stay in CompanionOrchestrator for now (see the FASE 2 plan).

    confirm_fn(action, action_param, description) -> PolicyDecision is how a
    CONFIRM-tier tool actually asks before running — see
    src/ui/confirmation_dialog.py for the real Qt-backed implementation wired
    in production (app.py). It's injected rather than imported directly so
    AgentCore stays Qt-free and easy to unit test. When None (the default —
    background/legacy callers, most existing tests), CONFIRM tools fall back
    to the old auto-approve behavior, unchanged.

    policy_manager (optional) is consulted BEFORE confirm_fn: a BLOCKED
    target is refused with no dialog at all, and a previously ALWAYS/SESSION-
    granted one skips the dialog and runs directly. Without a policy_manager,
    every CONFIRM call asks confirm_fn every single time (equivalent to
    everything always being freshly "once")."""

    def __init__(
        self,
        registry: ToolRegistry,
        event_bus: EventBus,
        confirm_fn: Optional[ConfirmFn] = None,
        policy_manager: Optional[PermissionPolicyManager] = None,
    ):
        self.registry = registry
        self.event_bus = event_bus
        self.confirm_fn = confirm_fn
        self.policy_manager = policy_manager

    def execute(self, action: str, action_param) -> bool:
        """Same contract as the old CompanionOrchestrator._execute_action:
        returns True if a tool actually ran and reported success. See
        execute_with_detail() for callers (the Agent Engine task loop, FASE
        8) that need more than a bare bool — e.g. what observe_screen
        actually saw, or a terminal tool's real output."""
        success, _ = self.execute_with_detail(action, action_param)
        return success

    def execute_with_detail(self, action: str, action_param) -> Tuple[bool, Optional[str]]:
        """Same permission/confirmation flow as execute(), but also returns
        a "detail" string when the dispatched tool provides one — a plain
        Callable[[Any], bool] dispatch still works unchanged (detail is
        None); a dispatch that returns (bool, str) instead of a bare bool
        (see e.g. src/core/tool_registry.py's _observe_screen/
        _run_terminal_tool) surfaces its detail here. Never changes what
        gets emitted on the EventBus — ACTION_EXECUTED/REJECTED stay
        bool-only by design (see tool_registry.py's TERMINAL_TOOL_EXECUTED
        for why a generic event can't carry this instead)."""
        if not action or action == "Nenhuma":
            return False, None

        spec = self.registry.get(action)
        if spec is None:
            return False, None  # unknown action — ignored safely, same as before

        self.event_bus.emit(ACTION_REQUESTED, action=action, action_param=action_param)

        if spec.tier == PermissionTier.CONFIRM:
            if not self._resolve_confirmation(action, action_param):
                return False, None
        elif spec.tier == PermissionTier.DANGEROUS:
            # No tool is DANGEROUS yet. Fail closed rather than silently running
            # something explicitly marked as needing a confirmation flow that
            # doesn't exist.
            self.event_bus.emit(ACTION_REJECTED, action=action, action_param=action_param)
            return False, None

        # Descriptive-only tools (observe_screen/translate_screen) have no dispatch
        # handler — vision/translation are triggered by keyword detection
        # elsewhere, not through this table — so they're known but never "run".
        success = False
        detail = None
        if spec.dispatch:
            try:
                raw = spec.dispatch(action_param)
                if isinstance(raw, tuple):
                    success, detail = bool(raw[0]), raw[1]
                else:
                    success = bool(raw)
            except Exception:
                # A malformed action_param that slips past a tool's own type
                # checks (or a bug in a future tool) must fail as an ordinary
                # rejected action, not raise out of execute() — the caller
                # (orchestrator's worker thread) does have its own catch-all,
                # but a tool crashing shouldn't depend on that outer net to
                # avoid skipping the ACTION_EXECUTED/REJECTED bookkeeping below.
                logging.error(f"Tool '{action}' raised while dispatching action_param={action_param!r}", exc_info=True)
        self.event_bus.emit(ACTION_EXECUTED if success else ACTION_REJECTED, action=action, action_param=action_param)
        return success, detail

    def _resolve_confirmation(self, action: str, action_param) -> bool:
        """Returns True if a CONFIRM-tier action may proceed to dispatch,
        emitting the PERMISSION_*/ACTION_REJECTED events along the way."""
        target = policy_target(action, action_param)

        if self.policy_manager and self.policy_manager.is_blocked(action, target):
            self.event_bus.emit(PERMISSION_DENIED, action=action, action_param=action_param)
            self.event_bus.emit(ACTION_REJECTED, action=action, action_param=action_param)
            return False

        if self.policy_manager and self.policy_manager.is_granted(action, target):
            # Already decided (ALWAYS persisted, or SESSION granted earlier
            # this run) — no dialog needed.
            self.event_bus.emit(PERMISSION_GRANTED, action=action, action_param=action_param)
            return True

        if self.confirm_fn is None:
            # No confirmation UI wired — auto-approve but flag it distinctly
            # from a plain SAFE execution (unchanged legacy behavior).
            self.event_bus.emit(ACTION_CONFIRM_AUTO_APPROVED, action=action, action_param=action_param)
            return True

        description = describe_action(action, action_param)
        self.event_bus.emit(PERMISSION_REQUESTED, action=action, action_param=action_param, description=description)
        decision = self.confirm_fn(action, action_param, description)

        if self.policy_manager:
            # set_policy already no-ops for ONCE/DECLINED on its own (see
            # PermissionPolicyManager) — no need to pre-filter here too.
            self.policy_manager.set_policy(action, target, decision)

        if decision not in _APPROVING_DECISIONS:
            self.event_bus.emit(PERMISSION_DENIED, action=action, action_param=action_param)
            self.event_bus.emit(ACTION_REJECTED, action=action, action_param=action_param)
            return False

        self.event_bus.emit(PERMISSION_GRANTED, action=action, action_param=action_param)
        return True
