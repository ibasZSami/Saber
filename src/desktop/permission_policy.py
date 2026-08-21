from enum import Enum
from typing import Optional


class PolicyDecision(str, Enum):
    """What the user chose (or what was already on file) for a CONFIRM-tier
    action against a specific target (an app name, a URL). ONCE and DECLINED
    never persist — every other request for the same (action, target) still
    asks from scratch. SESSION/ALWAYS/BLOCKED persist (see
    PermissionPolicyManager) and short-circuit future dialogs entirely."""

    ONCE = "once"
    SESSION = "session"
    ALWAYS = "always"
    BLOCKED = "blocked"
    DECLINED = "declined"


def policy_target(action: str, action_param) -> str:
    """Extracts what a policy is actually keyed on from a tool call's raw
    param — the app name for open_application/close_application, the app
    name from set_app_volume's dict, the raw URL for open_url. Lower-cased/
    stripped so 'Chrome' and 'chrome ' land on the same policy entry."""
    if isinstance(action_param, dict):
        target = action_param.get("application") or action_param.get("url") or ""
    else:
        target = action_param or ""
    return str(target).lower().strip()


class PermissionPolicyManager:
    """Per (action, target) confirmation policy — orchestrator-owned, not
    Qt-aware. Answers "does this specific app+action still need to ask, or
    was that already decided?", distinct from PermissionManager's allowlist
    (which answers "do we even know how to launch this app").

    ALWAYS/BLOCKED persist to Settings (config.json — survives restart).
    SESSION lives only in memory for this run (a fresh dict every
    construction is enough; nothing to clear on "logout" since there isn't
    one). ONCE/DECLINED are never stored — the whole point of "once" is that
    it asks again next time.
    """

    SETTINGS_KEY = "permission_policies"

    def __init__(self, settings=None):
        self.settings = settings
        self._persisted: dict = dict(settings.get(self.SETTINGS_KEY, {})) if settings else {}
        self._session: dict = {}

    @staticmethod
    def _key(action: str, target: str) -> str:
        return f"{action}:{target}"

    def get_policy(self, action: str, target: str) -> Optional[PolicyDecision]:
        key = self._key(action, target)
        if key in self._session:
            return self._session[key]
        raw = self._persisted.get(key)
        return PolicyDecision(raw) if raw else None

    def is_blocked(self, action: str, target: str) -> bool:
        return self.get_policy(action, target) == PolicyDecision.BLOCKED

    def is_granted(self, action: str, target: str) -> bool:
        return self.get_policy(action, target) in (PolicyDecision.ALWAYS, PolicyDecision.SESSION)

    def set_policy(self, action: str, target: str, decision: PolicyDecision) -> None:
        key = self._key(action, target)
        if decision == PolicyDecision.SESSION:
            self._session[key] = decision
            return
        if decision in (PolicyDecision.ALWAYS, PolicyDecision.BLOCKED):
            self._persisted[key] = decision.value
            self._session.pop(key, None)
            if self.settings:
                self.settings.set(self.SETTINGS_KEY, dict(self._persisted))
            return
        # ONCE / DECLINED: nothing to remember.

    def revoke(self, action: str, target: str) -> None:
        """Clears any stored decision (session or persisted) for (action,
        target), so the next request asks from scratch. Powers "permissões
        devem poder ser revogadas" — a Settings screen for listing/revoking
        these is Privacy Center (FASE 6) work, out of scope here; this is
        just the manager-level capability it will call."""
        key = self._key(action, target)
        self._session.pop(key, None)
        if key in self._persisted:
            del self._persisted[key]
            if self.settings:
                self.settings.set(self.SETTINGS_KEY, dict(self._persisted))

    def all_policies(self) -> dict:
        """Snapshot of every known policy (persisted + this session's) keyed
        by 'action:target' -> decision string. Read model for a future
        permissions list screen."""
        merged = dict(self._persisted)
        merged.update({key: decision.value for key, decision in self._session.items()})
        return merged
