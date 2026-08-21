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
        assert registry.tier_of("close_application") == PermissionTier.CONFIRM
        assert registry.tier_of("open_url") == PermissionTier.CONFIRM
        assert registry.tier_of("search_web") == PermissionTier.SAFE
        assert registry.tier_of("remember") == PermissionTier.SAFE
        assert registry.tier_of("forget_memory") == PermissionTier.SAFE
        assert registry.tier_of("set_app_volume") == PermissionTier.CONFIRM
        assert registry.tier_of("mouse_click") == PermissionTier.CONFIRM
        assert registry.tier_of("mouse_move") == PermissionTier.CONFIRM
        assert registry.tier_of("type_text") == PermissionTier.CONFIRM
        assert registry.tier_of("press_key") == PermissionTier.CONFIRM
        assert registry.tier_of("run_terminal_tool") == PermissionTier.CONFIRM

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

    def test_close_application_dispatch_calls_action_manager(self):
        action_manager, memory_manager = self._managers()
        action_manager.close_application.return_value = True
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("close_application").dispatch("chrome")

        action_manager.close_application.assert_called_once_with("chrome")
        assert result is True

    def test_close_application_dispatch_ignores_empty_param(self):
        action_manager, memory_manager = self._managers()
        registry = build_default_registry(action_manager, memory_manager)

        result = registry.get("close_application").dispatch("")

        action_manager.close_application.assert_not_called()
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


class TestSetAppVolumeDispatch:
    def _registry(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        audio_mixer_manager = MagicMock()
        registry = build_default_registry(action_manager, memory_manager, audio_mixer_manager)
        return registry, audio_mixer_manager

    def test_dispatch_converts_percent_to_fraction(self):
        registry, audio_mixer_manager = self._registry()
        audio_mixer_manager.set_volume.return_value = True

        result = registry.get("set_app_volume").dispatch({"application": "discord", "level": 20})

        audio_mixer_manager.set_volume.assert_called_once_with("discord", 0.2)
        assert result is True

    def test_dispatch_ignores_missing_application(self):
        registry, audio_mixer_manager = self._registry()

        result = registry.get("set_app_volume").dispatch({"level": 20})

        audio_mixer_manager.set_volume.assert_not_called()
        assert result is False

    def test_dispatch_ignores_missing_level(self):
        registry, audio_mixer_manager = self._registry()

        result = registry.get("set_app_volume").dispatch({"application": "discord"})

        audio_mixer_manager.set_volume.assert_not_called()
        assert result is False

    def test_dispatch_ignores_non_numeric_level(self):
        registry, audio_mixer_manager = self._registry()

        result = registry.get("set_app_volume").dispatch({"application": "discord", "level": "loud"})

        audio_mixer_manager.set_volume.assert_not_called()
        assert result is False

    def test_dispatch_ignores_non_dict_param(self):
        registry, audio_mixer_manager = self._registry()

        result = registry.get("set_app_volume").dispatch("discord")

        audio_mixer_manager.set_volume.assert_not_called()
        assert result is False

    def test_default_audio_mixer_manager_is_constructed_when_not_given(self):
        """build_default_registry(action_manager, memory_manager) without a third
        arg must keep working — existing callers shouldn't break."""
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        assert registry.get("set_app_volume").dispatch is not None


class TestResearchTopicDispatch:
    def _registry(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        background_task_manager = MagicMock()
        research_manager = MagicMock()
        registry = build_default_registry(
            action_manager, memory_manager,
            background_task_manager=background_task_manager,
            research_manager=research_manager,
        )
        return registry, background_task_manager, research_manager

    def test_dispatch_creates_a_background_task(self):
        registry, background_task_manager, research_manager = self._registry()
        background_task_manager.create_task.return_value = "task-123"

        result = registry.get("research_topic").dispatch("novidades do minecraft")

        assert result is True
        background_task_manager.create_task.assert_called_once()
        call_args = background_task_manager.create_task.call_args[0]
        assert call_args[0] == "research"
        assert call_args[1] == "novidades do minecraft"

    def test_dispatch_work_fn_calls_research_manager(self):
        registry, background_task_manager, research_manager = self._registry()
        research_manager.research.return_value = "resumo"

        registry.get("research_topic").dispatch("novidades do minecraft")

        work_fn = background_task_manager.create_task.call_args[0][2]
        assert work_fn() == "resumo"
        research_manager.research.assert_called_once_with("novidades do minecraft")

    def test_dispatch_ignores_empty_param(self):
        registry, background_task_manager, _ = self._registry()

        result = registry.get("research_topic").dispatch("")

        background_task_manager.create_task.assert_not_called()
        assert result is False

    def test_dispatch_strips_whitespace(self):
        registry, background_task_manager, _ = self._registry()

        registry.get("research_topic").dispatch("   query com espaço   ")

        call_args = background_task_manager.create_task.call_args[0]
        assert call_args[1] == "query com espaço"

    def test_no_dispatch_when_deps_not_provided(self):
        """Without background_task_manager/research_manager, research_topic
        stays known-but-not-wired, same as observe_screen/translate_screen."""
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        assert registry.get("research_topic").dispatch is None


class TestCreateReminderDispatch:
    def _registry(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        scheduler = MagicMock()
        registry = build_default_registry(action_manager, memory_manager, scheduler=scheduler)
        return registry, scheduler

    def test_dispatch_creates_a_reminder_via_the_scheduler(self):
        registry, scheduler = self._registry()

        result = registry.get("create_reminder").dispatch({"message": "tirar o bolo", "minutes_from_now": 10})

        assert result is True
        scheduler.create.assert_called_once()
        call_args = scheduler.create.call_args[0]
        assert call_args[0] == "tirar o bolo"

    def test_dispatch_rejects_missing_message(self):
        registry, scheduler = self._registry()
        result = registry.get("create_reminder").dispatch({"minutes_from_now": 10})
        assert result is False
        scheduler.create.assert_not_called()

    def test_dispatch_rejects_non_numeric_minutes(self):
        registry, scheduler = self._registry()
        result = registry.get("create_reminder").dispatch({"message": "x", "minutes_from_now": "logo"})
        assert result is False
        scheduler.create.assert_not_called()

    def test_dispatch_rejects_non_positive_minutes(self):
        registry, scheduler = self._registry()
        result = registry.get("create_reminder").dispatch({"message": "x", "minutes_from_now": 0})
        assert result is False
        scheduler.create.assert_not_called()

    def test_dispatch_rejects_non_dict_param(self):
        registry, scheduler = self._registry()
        result = registry.get("create_reminder").dispatch("x")
        assert result is False
        scheduler.create.assert_not_called()

    def test_no_dispatch_when_scheduler_not_provided(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        assert registry.get("create_reminder").dispatch is None


class TestMouseAndKeyboardDispatch:
    def _registry(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        input_controller = MagicMock()
        registry = build_default_registry(action_manager, memory_manager, input_controller=input_controller)
        return registry, input_controller

    def test_mouse_click_dispatch_calls_input_controller(self):
        registry, input_controller = self._registry()
        input_controller.click.return_value = True

        result = registry.get("mouse_click").dispatch({"x": 100, "y": 200, "button": "right"})

        assert result is True
        input_controller.click.assert_called_once_with(100, 200, button="right")

    def test_mouse_click_defaults_to_left_button(self):
        registry, input_controller = self._registry()
        registry.get("mouse_click").dispatch({"x": 10, "y": 20})
        input_controller.click.assert_called_once_with(10, 20, button="left")

    def test_mouse_click_rejects_out_of_range_coordinates(self):
        registry, input_controller = self._registry()
        result = registry.get("mouse_click").dispatch({"x": 999999, "y": 20})
        assert result is False
        input_controller.click.assert_not_called()

    def test_mouse_click_rejects_non_numeric_coordinates(self):
        registry, input_controller = self._registry()
        result = registry.get("mouse_click").dispatch({"x": "abc", "y": 20})
        assert result is False
        input_controller.click.assert_not_called()

    def test_mouse_click_rejects_non_dict_param(self):
        registry, input_controller = self._registry()
        result = registry.get("mouse_click").dispatch("100,200")
        assert result is False
        input_controller.click.assert_not_called()

    def test_mouse_move_dispatch_calls_input_controller(self):
        registry, input_controller = self._registry()
        input_controller.move.return_value = True
        result = registry.get("mouse_move").dispatch({"x": 5, "y": 6})
        assert result is True
        input_controller.move.assert_called_once_with(5, 6)

    def test_type_text_dispatch_calls_input_controller(self):
        registry, input_controller = self._registry()
        input_controller.type_text.return_value = True
        result = registry.get("type_text").dispatch({"text": "olá"})
        assert result is True
        input_controller.type_text.assert_called_once_with("olá")

    def test_type_text_rejects_empty_string(self):
        registry, input_controller = self._registry()
        result = registry.get("type_text").dispatch({"text": ""})
        assert result is False
        input_controller.type_text.assert_not_called()

    def test_press_key_dispatch_calls_input_controller(self):
        registry, input_controller = self._registry()
        input_controller.press_key.return_value = True
        result = registry.get("press_key").dispatch({"key": "Enter"})
        assert result is True
        input_controller.press_key.assert_called_once_with("Enter")

    def test_press_key_rejects_missing_key(self):
        registry, input_controller = self._registry()
        result = registry.get("press_key").dispatch({})
        assert result is False
        input_controller.press_key.assert_not_called()

    def test_no_dispatch_when_input_controller_not_provided(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        assert registry.get("mouse_click").dispatch is None
        assert registry.get("mouse_move").dispatch is None
        assert registry.get("type_text").dispatch is None
        assert registry.get("press_key").dispatch is None


class TestRunTerminalToolDispatch:
    def _registry(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        terminal_tool_manager = MagicMock()
        registry = build_default_registry(action_manager, memory_manager, terminal_tool_manager=terminal_tool_manager)
        return registry, terminal_tool_manager

    def test_dispatch_calls_terminal_tool_manager(self):
        registry, terminal_tool_manager = self._registry()
        terminal_tool_manager.run.return_value = {"success": True, "output": "ok", "error": None}

        result = registry.get("run_terminal_tool").dispatch({"name": "nmap", "args": "-sV localhost"})

        assert result == (True, "ok")
        terminal_tool_manager.run.assert_called_once_with("nmap", "-sV localhost")

    def test_dispatch_defaults_args_to_empty_string(self):
        registry, terminal_tool_manager = self._registry()
        terminal_tool_manager.run.return_value = {"success": True, "output": "", "error": None}
        registry.get("run_terminal_tool").dispatch({"name": "nmap"})
        terminal_tool_manager.run.assert_called_once_with("nmap", "")

    def test_dispatch_reflects_failure(self):
        registry, terminal_tool_manager = self._registry()
        terminal_tool_manager.run.return_value = {"success": False, "output": "", "error": "não permitido"}
        result = registry.get("run_terminal_tool").dispatch({"name": "not_allowed"})
        assert result == (False, "não permitido")

    def test_dispatch_rejects_missing_name(self):
        registry, terminal_tool_manager = self._registry()
        result = registry.get("run_terminal_tool").dispatch({"args": "x"})
        assert result == (False, None)
        terminal_tool_manager.run.assert_not_called()

    def test_dispatch_rejects_non_dict_param(self):
        registry, terminal_tool_manager = self._registry()
        result = registry.get("run_terminal_tool").dispatch("nmap")
        assert result == (False, None)
        terminal_tool_manager.run.assert_not_called()

    def test_no_dispatch_when_terminal_tool_manager_not_provided(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        assert registry.get("run_terminal_tool").dispatch is None


class TestObserveScreenDispatch:
    def _registry(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        screen_capture = MagicMock()
        ocr_provider = MagicMock()
        registry = build_default_registry(
            action_manager, memory_manager, screen_capture=screen_capture, ocr_provider=ocr_provider,
        )
        return registry, screen_capture, ocr_provider

    def test_dispatch_returns_the_ocr_text_as_detail(self):
        registry, screen_capture, ocr_provider = self._registry()
        ocr_provider.extract_text.return_value = {"text": "Game Over", "confidence": 0.9}

        spec = registry.get("observe_screen")
        result = spec.dispatch("")

        assert result == (True, "Game Over")

    def test_dispatch_fails_when_no_text_found(self):
        registry, screen_capture, ocr_provider = self._registry()
        ocr_provider.extract_text.return_value = {"text": "", "error": "sem texto"}

        result = registry.get("observe_screen").dispatch("")

        assert result == (False, "sem texto")

    def test_dispatch_handles_capture_exception(self):
        registry, screen_capture, ocr_provider = self._registry()
        screen_capture.capture_primary.side_effect = RuntimeError("boom")

        success, detail = registry.get("observe_screen").dispatch("")

        assert success is False
        assert "boom" in detail

    def test_no_dispatch_when_deps_not_provided(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        assert registry.get("observe_screen").dispatch is None

    def test_no_dispatch_when_only_screen_capture_provided(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager, screen_capture=MagicMock())
        assert registry.get("observe_screen").dispatch is None


class TestActivateTranslationModeDispatch:
    def test_dispatch_starts_translation_mode(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        translation_mode = MagicMock()
        registry = build_default_registry(action_manager, memory_manager, translation_mode=translation_mode)

        result = registry.get("activate_translation_mode").dispatch("")

        assert result is True
        translation_mode.start.assert_called_once()

    def test_no_dispatch_when_translation_mode_not_provided(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        assert registry.get("activate_translation_mode").dispatch is None


class TestAsToolsSchemaDispatchableOnly:
    def test_excludes_tools_without_a_dispatch_handler(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)  # no scheduler/input/terminal

        names = {entry["name"] for entry in registry.as_tools_schema(dispatchable_only=True)}

        assert "search_web" in names
        assert "observe_screen" not in names  # no screen_capture/ocr_provider provided
        assert "create_reminder" not in names  # no scheduler provided
        assert "mouse_click" not in names  # no input_controller provided
        assert "run_terminal_tool" not in names  # no terminal_tool_manager provided
        assert "translate_screen" not in names  # never has a dispatch handler at all

    def test_includes_everything_when_all_dependencies_are_wired(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(
            action_manager, memory_manager,
            scheduler=MagicMock(), input_controller=MagicMock(), terminal_tool_manager=MagicMock(),
            screen_capture=MagicMock(), ocr_provider=MagicMock(), translation_mode=MagicMock(),
        )

        names = {entry["name"] for entry in registry.as_tools_schema(dispatchable_only=True)}

        assert "mouse_click" in names
        assert "create_reminder" in names
        assert "run_terminal_tool" in names
        assert "observe_screen" in names
        assert "activate_translation_mode" in names
        assert "translate_screen" not in names  # still descriptive-only regardless

    def test_default_false_keeps_every_tool(self):
        action_manager, memory_manager = MagicMock(), MagicMock()
        registry = build_default_registry(action_manager, memory_manager)
        names = {entry["name"] for entry in registry.as_tools_schema()}
        assert "mouse_click" in names
        assert "observe_screen" in names


class TestDescribeTools:
    def test_returns_every_tool_with_name_and_description(self):
        schema = describe_tools()
        names = {entry["name"] for entry in schema}
        assert names == {
            "observe_screen", "translate_screen", "open_application", "close_application",
            "open_url", "search_web", "remember", "forget_memory", "set_app_volume", "research_topic",
            "create_reminder", "mouse_click", "mouse_move", "type_text", "press_key", "run_terminal_tool",
            "activate_translation_mode",
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
