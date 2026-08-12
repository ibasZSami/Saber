from unittest.mock import MagicMock

from src.core.tool_registry import PermissionTier, ToolRegistry, ToolSpec, build_default_registry


class TestToolRegistry:
    def test_unknown_tool_returns_none(self):
        registry = ToolRegistry()
        assert registry.get("fly_to_moon") is None
        assert registry.tier_of("fly_to_moon") is None

    def test_register_and_get(self):
        registry = ToolRegistry()
        spec = ToolSpec(name="noop", tier=PermissionTier.SAFE, description="", dispatch=lambda p: True)
        registry.register(spec)
        assert registry.get("noop") is spec
        assert registry.tier_of("noop") == PermissionTier.SAFE


class TestBuildDefaultRegistry:
    def _managers(self):
        return MagicMock(name="action_manager"), MagicMock(name="memory_manager")

    def test_tiers_match_the_approved_plan(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        assert registry.tier_of("open_application") == PermissionTier.CONFIRM
        assert registry.tier_of("open_url") == PermissionTier.CONFIRM
        assert registry.tier_of("search_web") == PermissionTier.SAFE
        assert registry.tier_of("remember") == PermissionTier.SAFE
        assert registry.tier_of("forget_memory") == PermissionTier.SAFE

    def test_open_application_dispatch_calls_action_manager(self):
        action_manager, memory_manager = self._managers()
        action_manager.open_application.return_value = True
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("open_application").dispatch("chrome")

        action_manager.open_application.assert_called_once_with("chrome")
        assert result is True

    def test_open_application_dispatch_ignores_empty_param(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("open_application").dispatch("")

        action_manager.open_application.assert_not_called()
        assert result is False

    def test_open_url_dispatch(self):
        action_manager, memory_manager = self._managers()
        action_manager.open_url.return_value = True
        registry = build_default_registry(action_manager, memory_manager)

        assert registry.get("open_url").dispatch("https://example.com") is True
        action_manager.open_url.assert_called_once_with("https://example.com")

    def test_search_web_dispatch(self):
        action_manager, memory_manager = self._managers()
        action_manager.search_web.return_value = True
        registry = build_default_registry(action_manager, memory_manager)

        assert registry.get("search_web").dispatch("python") is True
        action_manager.search_web.assert_called_once_with("python")

    def test_remember_dispatch_with_valid_dict(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("remember").dispatch({"key": "cor_favorita", "value": "roxo"})

        memory_manager.remember.assert_called_once_with("cor_favorita", "roxo")
        assert result is True

    def test_remember_dispatch_without_key_is_ignored(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("remember").dispatch({"value": "roxo"})

        memory_manager.remember.assert_not_called()
        assert result is False

    def test_forget_memory_dispatch_with_dict_param(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("forget_memory").dispatch({"key": "cor_favorita"})

        memory_manager.forget.assert_called_once_with("cor_favorita")
        assert result is True

    def test_forget_memory_dispatch_with_plain_string_param(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("forget_memory").dispatch("cor_favorita")

        memory_manager.forget.assert_called_once_with("cor_favorita")
        assert result is True
