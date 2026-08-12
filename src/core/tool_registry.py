from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class PermissionTier(str, Enum):
    SAFE = "SAFE"
    CONFIRM = "CONFIRM"
    DANGEROUS = "DANGEROUS"  # reserved — no tool uses this yet


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tier: PermissionTier
    description: str
    dispatch: Optional[Callable[[Any], bool]]  # (action_param) -> True if it actually ran
    parameters: Optional[Dict[str, str]] = None


class ToolRegistry:
    """Maps a tool name to its permission tier and handler — replaces the old
    if/elif dispatch chain in orchestrator.py with a real, inspectable table."""

    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def tier_of(self, name: str) -> Optional[PermissionTier]:
        spec = self._tools.get(name)
        return spec.tier if spec else None

    def as_tools_schema(self) -> List[Dict[str, Any]]:
        """Rebuilds the prompt-facing {name, description, parameters} shape from
        the registered specs, so the AI-facing schema and the dispatch table can't
        drift apart the way two hand-kept-in-sync lists eventually would."""
        schema = []
        for spec in self._tools.values():
            entry = {"name": spec.name, "description": spec.description}
            if spec.parameters:
                entry["parameters"] = spec.parameters
            schema.append(entry)
        return schema


# Static metadata for every tool the AI can be told about — including
# observe_screen/translate_screen, which are descriptive-only (vision/translation
# are actually triggered by keyword detection elsewhere, not through this dispatch
# table) and so are registered with no dispatch handler.
_TOOL_DEFS = [
    {
        "name": "observe_screen",
        "tier": PermissionTier.SAFE,
        "description": "Obtém uma análise da tela atual.",
    },
    {
        "name": "translate_screen",
        "tier": PermissionTier.SAFE,
        "description": "Captura a tela, executa OCR e traduz o texto selecionado.",
    },
    {
        "name": "open_application",
        "tier": PermissionTier.CONFIRM,
        "description": "Abre um aplicativo configurado na allowlist (ex: chrome, discord, vscode).",
        "parameters": {"application": "string"},
    },
    {
        "name": "open_url",
        "tier": PermissionTier.CONFIRM,
        "description": "Abre uma URL no navegador padrão.",
        "parameters": {"url": "string"},
    },
    {
        "name": "search_web",
        "tier": PermissionTier.SAFE,
        "description": "Pesquisa na web por um termo.",
        "parameters": {"query": "string"},
    },
    {
        "name": "remember",
        "tier": PermissionTier.SAFE,
        "description": "Salva uma informação importante na memória de longo prazo.",
        "parameters": {"key": "string", "value": "string"},
    },
    {
        "name": "forget_memory",
        "tier": PermissionTier.SAFE,
        "description": "Remove uma informação da memória.",
        "parameters": {"key": "string"},
    },
]


def describe_tools() -> List[Dict[str, Any]]:
    """Static tool metadata for prompt-building — unlike build_default_registry(),
    this needs no live manager instances, since it's pure description."""
    registry = ToolRegistry()
    for tool_def in _TOOL_DEFS:
        registry.register(ToolSpec(
            name=tool_def["name"],
            tier=tool_def["tier"],
            description=tool_def["description"],
            dispatch=None,
            parameters=tool_def.get("parameters"),
        ))
    return registry.as_tools_schema()


def _open_application(action_manager, action_param) -> bool:
    if not action_param:
        return False
    return bool(action_manager.open_application(action_param))


def _open_url(action_manager, action_param) -> bool:
    if not action_param:
        return False
    return bool(action_manager.open_url(action_param))


def _search_web(action_manager, action_param) -> bool:
    if not action_param:
        return False
    return bool(action_manager.search_web(action_param))


def _remember(memory_manager, action_param) -> bool:
    if isinstance(action_param, dict) and action_param.get("key"):
        memory_manager.remember(action_param["key"], action_param.get("value", ""))
        return True
    return False


def _forget_memory(memory_manager, action_param) -> bool:
    if not action_param:
        return False
    key = action_param.get("key") if isinstance(action_param, dict) else action_param
    memory_manager.forget(key)
    return True


# Tool names with a real dispatch handler — observe_screen/translate_screen are
# deliberately absent (see _TOOL_DEFS' comment above).
_DISPATCH_BUILDERS = {
    "open_application": lambda action_manager, memory_manager: (lambda p: _open_application(action_manager, p)),
    "open_url": lambda action_manager, memory_manager: (lambda p: _open_url(action_manager, p)),
    "search_web": lambda action_manager, memory_manager: (lambda p: _search_web(action_manager, p)),
    "remember": lambda action_manager, memory_manager: (lambda p: _remember(memory_manager, p)),
    "forget_memory": lambda action_manager, memory_manager: (lambda p: _forget_memory(memory_manager, p)),
}


def build_default_registry(action_manager, memory_manager) -> ToolRegistry:
    """Registers every tool from _TOOL_DEFS, binding a real dispatch handler for
    the ones that have one. Each dispatch guard reproduces the original
    CompanionOrchestrator._execute_action if/elif's truthiness/shape checks
    exactly, so wiring this in changes nothing about what executes — only how
    it's looked up and what permission tier it's tagged with."""
    registry = ToolRegistry()
    for tool_def in _TOOL_DEFS:
        build_dispatch = _DISPATCH_BUILDERS.get(tool_def["name"])
        dispatch = build_dispatch(action_manager, memory_manager) if build_dispatch else None
        registry.register(ToolSpec(
            name=tool_def["name"],
            tier=tool_def["tier"],
            description=tool_def["description"],
            dispatch=dispatch,
            parameters=tool_def.get("parameters"),
        ))
    return registry
