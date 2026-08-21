"""Plugin system — a minimal, deliberately small extension point. A plugin
is a single Python file under plugins/ exposing a module-level
`register(context)` function that adds one or more tools.

Security note, stated plainly rather than hidden: a plugin is arbitrary
Python code loaded from disk and executed in-process — this is NOT a
sandbox. A plugin's dispatch function can do anything ordinary Python code
can do, same as any file already in this repo; it does not go through
subprocess/allowlist restrictions the way run_terminal_tool does unless the
plugin author chooses to build it that way. The only real safety boundary
is PluginManager itself never running unless the user explicitly opts in
(plugins_enabled=False by default, same "opt-in before anything loads"
pattern already used for mouse/keyboard/terminal/browser) — install
plugins the same way you'd install any other software: only from a source
you trust."""

import importlib.util
import logging
import os
from dataclasses import dataclass
from typing import Callable, List, Tuple

from src.core.tool_registry import ToolSpec


@dataclass(frozen=True)
class PluginContext:
    """What a plugin receives — deliberately narrow: no access to the
    orchestrator or other subsystems, just enough to add a tool (which
    still goes through the same ToolRegistry/AgentCore CONFIRM/policy flow
    as every built-in tool once registered) and react to app events."""

    register_tool: Callable[[ToolSpec], None]
    event_bus: object
    settings: object


class PluginManager:
    def __init__(self, plugins_dir: str, tool_registry, event_bus, settings):
        self.plugins_dir = plugins_dir
        self.tool_registry = tool_registry
        self.event_bus = event_bus
        self.settings = settings
        self.loaded_plugins: List[str] = []
        self.failed_plugins: List[Tuple[str, str]] = []

    def load_all(self):
        if not os.path.isdir(self.plugins_dir):
            return
        for filename in sorted(os.listdir(self.plugins_dir)):
            if filename.endswith(".py") and not filename.startswith("_"):
                self._load_one(filename)

    def _load_one(self, filename: str):
        name = filename[:-3]
        path = os.path.join(self.plugins_dir, filename)
        try:
            spec = importlib.util.spec_from_file_location(f"silva_plugin_{name}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            register_fn = getattr(module, "register", None)
            if not callable(register_fn):
                raise AttributeError(f"Plugin '{name}' não define uma função register(context).")

            context = PluginContext(
                register_tool=self.tool_registry.register,
                event_bus=self.event_bus,
                settings=self.settings,
            )
            register_fn(context)
            self.loaded_plugins.append(name)
            logging.info(f"Plugin '{name}' carregado.")
        except Exception as e:
            # A broken plugin must never take the app down with it — every
            # failure is contained per-file and just excludes that one
            # plugin, same defense-in-depth already used for a crashing
            # tool dispatch (see AgentCore.execute_with_detail).
            logging.error(f"Falha ao carregar plugin '{name}': {e}", exc_info=True)
            self.failed_plugins.append((name, str(e)))
