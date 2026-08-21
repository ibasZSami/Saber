from src.desktop.permission_policy import PermissionPolicyManager, PolicyDecision, policy_target


class _FakeSettings:
    """Minimal Settings stand-in — a dict-backed get/set, same shape the real
    src/config/settings.py exposes."""

    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class TestPolicyTarget:
    def test_extracts_plain_string_param(self):
        assert policy_target("open_application", "Chrome") == "chrome"

    def test_extracts_application_key_from_dict_param(self):
        assert policy_target("set_app_volume", {"application": "Spotify", "level": 50}) == "spotify"

    def test_extracts_url_key_from_dict_param_when_no_application_key(self):
        assert policy_target("open_url", {"url": "https://Example.com"}) == "https://example.com"

    def test_strips_whitespace(self):
        assert policy_target("open_application", "  chrome  ") == "chrome"

    def test_empty_param_yields_empty_target(self):
        assert policy_target("open_application", None) == ""


class TestPermissionPolicyManagerInMemory:
    def test_unknown_target_has_no_policy(self):
        manager = PermissionPolicyManager()
        assert manager.get_policy("open_application", "chrome") is None
        assert manager.is_blocked("open_application", "chrome") is False
        assert manager.is_granted("open_application", "chrome") is False

    def test_blocked_is_blocked_not_granted(self):
        manager = PermissionPolicyManager()
        manager.set_policy("open_application", "chrome", PolicyDecision.BLOCKED)
        assert manager.is_blocked("open_application", "chrome") is True
        assert manager.is_granted("open_application", "chrome") is False

    def test_always_is_granted_not_blocked(self):
        manager = PermissionPolicyManager()
        manager.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)
        assert manager.is_granted("open_application", "chrome") is True
        assert manager.is_blocked("open_application", "chrome") is False

    def test_session_is_granted(self):
        manager = PermissionPolicyManager()
        manager.set_policy("open_application", "chrome", PolicyDecision.SESSION)
        assert manager.is_granted("open_application", "chrome") is True

    def test_once_and_declined_are_not_stored(self):
        manager = PermissionPolicyManager()
        manager.set_policy("open_application", "chrome", PolicyDecision.ONCE)
        manager.set_policy("open_application", "firefox", PolicyDecision.DECLINED)

        assert manager.get_policy("open_application", "chrome") is None
        assert manager.get_policy("open_application", "firefox") is None

    def test_different_actions_on_the_same_app_are_independent(self):
        """Matches the spec example: Chrome{Abrir: permitido, Fechar:
        confirmar} — one action's policy must not leak into another's."""
        manager = PermissionPolicyManager()
        manager.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)

        assert manager.is_granted("open_application", "chrome") is True
        assert manager.is_granted("close_application", "chrome") is False

    def test_revoke_clears_a_session_grant(self):
        manager = PermissionPolicyManager()
        manager.set_policy("open_application", "chrome", PolicyDecision.SESSION)

        manager.revoke("open_application", "chrome")

        assert manager.get_policy("open_application", "chrome") is None

    def test_revoke_on_unknown_target_does_not_raise(self):
        manager = PermissionPolicyManager()
        manager.revoke("open_application", "never_asked_about_this")  # must not raise

    def test_all_policies_merges_session_and_persisted(self):
        manager = PermissionPolicyManager()
        manager.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)
        manager.set_policy("close_application", "discord", PolicyDecision.SESSION)

        snapshot = manager.all_policies()

        assert snapshot == {
            "open_application:chrome": "always",
            "close_application:discord": "session",
        }


class TestPermissionPolicyManagerPersistence:
    def test_always_is_written_to_settings(self):
        settings = _FakeSettings()
        manager = PermissionPolicyManager(settings)

        manager.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)

        assert settings.get("permission_policies") == {"open_application:chrome": "always"}

    def test_blocked_is_written_to_settings(self):
        settings = _FakeSettings()
        manager = PermissionPolicyManager(settings)

        manager.set_policy("open_application", "chrome", PolicyDecision.BLOCKED)

        assert settings.get("permission_policies") == {"open_application:chrome": "blocked"}

    def test_session_is_not_written_to_settings(self):
        settings = _FakeSettings()
        manager = PermissionPolicyManager(settings)

        manager.set_policy("open_application", "chrome", PolicyDecision.SESSION)

        assert settings.get("permission_policies", {}) == {}

    def test_loads_existing_policies_from_settings_on_construction(self):
        settings = _FakeSettings({"permission_policies": {"open_application:chrome": "always"}})

        manager = PermissionPolicyManager(settings)

        assert manager.is_granted("open_application", "chrome") is True

    def test_revoke_persists_the_removal(self):
        settings = _FakeSettings({"permission_policies": {"open_application:chrome": "always"}})
        manager = PermissionPolicyManager(settings)

        manager.revoke("open_application", "chrome")

        assert settings.get("permission_policies") == {}

    def test_new_manager_instance_sees_a_prior_instances_persisted_policy(self):
        """Simulates surviving an app restart: a fresh PermissionPolicyManager
        built on the same Settings must see what an earlier one persisted."""
        settings = _FakeSettings()
        PermissionPolicyManager(settings).set_policy("open_application", "chrome", PolicyDecision.ALWAYS)

        manager = PermissionPolicyManager(settings)

        assert manager.is_granted("open_application", "chrome") is True

    def test_works_without_settings_at_all(self):
        """No Settings injected — everything still works, just in-memory only
        (matches how AgentCore's confirm_fn=None fallback has no UI either)."""
        manager = PermissionPolicyManager(settings=None)

        manager.set_policy("open_application", "chrome", PolicyDecision.ALWAYS)

        assert manager.is_granted("open_application", "chrome") is True
