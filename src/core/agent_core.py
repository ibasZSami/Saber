from src.core.event_bus import (
    EventBus,
    ACTION_REQUESTED,
    ACTION_EXECUTED,
    ACTION_REJECTED,
    ACTION_CONFIRM_AUTO_APPROVED,
)
from src.core.tool_registry import PermissionTier, ToolRegistry


class AgentCore:
    """Owns tool dispatch: turns a parsed (action, action_param) into a real
    side effect through the ToolRegistry, enforcing permission tiers first.
    Deliberately does NOT own AI calls, memory history, TTS, or vision — those
    stay in CompanionOrchestrator for now (see the FASE 2 plan)."""

    def __init__(self, registry: ToolRegistry, event_bus: EventBus):
        self.registry = registry
        self.event_bus = event_bus

    def execute(self, action: str, action_param) -> bool:
        """Same contract as the old CompanionOrchestrator._execute_action:
        returns True if a tool actually ran and reported success."""
        if not action or action == "Nenhuma":
            return False

        spec = self.registry.get(action)
        if spec is None:
            return False  # unknown action — ignored safely, same as before

        self.event_bus.emit(ACTION_REQUESTED, action=action, action_param=action_param)

        if spec.tier == PermissionTier.CONFIRM:
            # No confirmation UI exists yet — auto-approve but flag it distinctly
            # from a plain SAFE execution, so a future dialog has one seam to
            # intercept instead of silently blocking something that works today.
            self.event_bus.emit(ACTION_CONFIRM_AUTO_APPROVED, action=action, action_param=action_param)
        elif spec.tier == PermissionTier.DANGEROUS:
            # No tool is DANGEROUS yet. Fail closed rather than silently running
            # something explicitly marked as needing a confirmation flow that
            # doesn't exist.
            self.event_bus.emit(ACTION_REJECTED, action=action, action_param=action_param)
            return False

        success = bool(spec.dispatch(action_param))
        self.event_bus.emit(ACTION_EXECUTED if success else ACTION_REJECTED, action=action, action_param=action_param)
        return success
