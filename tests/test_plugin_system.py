from unittest.mock import MagicMock

from src.core.plugin_system import PluginManager
from src.core.tool_registry import PermissionTier


def _write_plugin(tmp_path, filename, content):
    (tmp_path / filename).write_text(content, encoding="utf-8")


VALID_PLUGIN = """
from src.core.tool_registry import ToolSpec, PermissionTier

def register(context):
    context.register_tool(ToolSpec(
        name="roll_dice",
        tier=PermissionTier.SAFE,
        description="Rola um dado",
        dispatch=lambda p: True,
    ))
"""

PLUGIN_WITHOUT_REGISTER = """
x = 1
"""

PLUGIN_THAT_RAISES = """
def register(context):
    raise RuntimeError("plugin quebrado")
"""

PLUGIN_WITH_SYNTAX_ERROR = """
def register(context)
    pass
"""


class TestLoadAll:
    def test_missing_plugins_dir_does_nothing(self, tmp_path):
        manager = PluginManager(str(tmp_path / "does_not_exist"), MagicMock(), MagicMock(), MagicMock())
        manager.load_all()  # should not raise
        assert manager.loaded_plugins == []

    def test_loads_a_valid_plugin_and_registers_its_tool(self, tmp_path):
        _write_plugin(tmp_path, "dice.py", VALID_PLUGIN)
        tool_registry = MagicMock()
        manager = PluginManager(str(tmp_path), tool_registry, MagicMock(), MagicMock())

        manager.load_all()

        assert manager.loaded_plugins == ["dice"]
        tool_registry.register.assert_called_once()
        registered_spec = tool_registry.register.call_args[0][0]
        assert registered_spec.name == "roll_dice"
        assert registered_spec.tier == PermissionTier.SAFE

    def test_ignores_non_python_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not a plugin", encoding="utf-8")
        manager = PluginManager(str(tmp_path), MagicMock(), MagicMock(), MagicMock())
        manager.load_all()
        assert manager.loaded_plugins == []

    def test_ignores_files_starting_with_underscore(self, tmp_path):
        _write_plugin(tmp_path, "_helper.py", VALID_PLUGIN)
        manager = PluginManager(str(tmp_path), MagicMock(), MagicMock(), MagicMock())
        manager.load_all()
        assert manager.loaded_plugins == []

    def test_plugin_without_register_function_fails_cleanly(self, tmp_path):
        _write_plugin(tmp_path, "broken.py", PLUGIN_WITHOUT_REGISTER)
        manager = PluginManager(str(tmp_path), MagicMock(), MagicMock(), MagicMock())

        manager.load_all()  # should not raise

        assert manager.loaded_plugins == []
        assert len(manager.failed_plugins) == 1
        assert manager.failed_plugins[0][0] == "broken"

    def test_plugin_that_raises_during_register_fails_cleanly_not_taking_others_down(self, tmp_path):
        _write_plugin(tmp_path, "a_broken.py", PLUGIN_THAT_RAISES)
        _write_plugin(tmp_path, "b_valid.py", VALID_PLUGIN)
        manager = PluginManager(str(tmp_path), MagicMock(), MagicMock(), MagicMock())

        manager.load_all()  # should not raise

        assert "b_valid" in manager.loaded_plugins
        assert any(name == "a_broken" for name, _ in manager.failed_plugins)

    def test_plugin_with_a_syntax_error_fails_cleanly(self, tmp_path):
        _write_plugin(tmp_path, "syntax_error.py", PLUGIN_WITH_SYNTAX_ERROR)
        manager = PluginManager(str(tmp_path), MagicMock(), MagicMock(), MagicMock())

        manager.load_all()  # should not raise

        assert manager.loaded_plugins == []
        assert len(manager.failed_plugins) == 1

    def test_context_gives_the_plugin_the_real_event_bus_and_settings(self, tmp_path):
        plugin_source = """
def register(context):
    context.event_bus.emit("PLUGIN_TEST_EVENT", value=context.settings.get("some_key"))
"""
        _write_plugin(tmp_path, "uses_context.py", plugin_source)
        event_bus = MagicMock()
        settings = MagicMock()
        settings.get.return_value = "hello"
        manager = PluginManager(str(tmp_path), MagicMock(), event_bus, settings)

        manager.load_all()

        event_bus.emit.assert_called_once_with("PLUGIN_TEST_EVENT", value="hello")

    def test_multiple_valid_plugins_all_load(self, tmp_path):
        _write_plugin(tmp_path, "one.py", VALID_PLUGIN)
        _write_plugin(tmp_path, "two.py", VALID_PLUGIN.replace("roll_dice", "roll_dice_2"))
        manager = PluginManager(str(tmp_path), MagicMock(), MagicMock(), MagicMock())

        manager.load_all()

        assert set(manager.loaded_plugins) == {"one", "two"}


class TestRealPluginsFolder:
    """The actual plugins/ folder shipped in this repo must itself load
    cleanly — a regression here means the shipped example is broken for
    every user who turns plugins on."""

    def test_the_real_plugins_directory_loads_without_errors(self):
        import os
        from src.core.tool_registry import ToolRegistry
        plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
        tool_registry = ToolRegistry()
        manager = PluginManager(plugins_dir, tool_registry, MagicMock(), MagicMock())

        manager.load_all()

        assert manager.failed_plugins == []
        assert "example_dice" in manager.loaded_plugins
        assert tool_registry.get("roll_dice") is not None

    def test_the_example_dice_tool_actually_works(self):
        import os
        from src.core.tool_registry import ToolRegistry
        plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
        tool_registry = ToolRegistry()
        PluginManager(plugins_dir, tool_registry, MagicMock(), MagicMock()).load_all()

        success, detail = tool_registry.get("roll_dice").dispatch({"sides": 20})

        assert success is True
        assert "dado de 20 lados" in detail
