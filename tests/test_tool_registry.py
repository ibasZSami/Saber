from unittest.mock import MagicMock

from src.core.tool_registry import PermissionTier, ToolRegistry, ToolSpec, build_default_registry, describe_tools


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

    def test_descriptive_only_tools_have_no_dispatch_handler(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        assert registry.get("observe_screen").dispatch is None
        assert registry.get("translate_screen").dispatch is None


class TestDescribeTools:
    def test_returns_every_tool_with_name_and_description(self):
        schema = describe_tools()
        names = {entry["name"] for entry in schema}
        assert names == {
            "observe_screen", "translate_screen", "open_application",
            "open_url", "search_web", "remember", "forget_memory",
        }
        assert all("description" in entry for entry in schema)

    def test_tools_with_parameters_include_them(self):
        schema = describe_tools()
        by_name = {entry["name"]: entry for entry in schema}
        assert by_name["open_application"]["parameters"] == {"application": "string"}
        assert by_name["remember"]["parameters"] == {"key": "string", "value": "string"}

    def test_descriptive_only_tools_have_no_parameters_key(self):
        schema = describe_tools()
        by_name = {entry["name"]: entry for entry in schema}
        assert "parameters" not in by_name["observe_screen"]

    def test_matches_registry_dispatch_table_tiers(self):
        """The prompt-facing schema and the dispatch registry are built from the
        same source (_TOOL_DEFS), so tool names can't silently drift apart."""
        registry = build_default_registry(MagicMock(), MagicMock())
        schema_names = {entry["name"] for entry in describe_tools()}
        registry_names = {entry["name"] for entry in registry.as_tools_schema()}
        assert schema_names == registry_names
