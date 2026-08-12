from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional


class PermissionTier(str, Enum):
    SAFE = "SAFE"
    CONFIRM = "CONFIRM"
    DANGEROUS = "DANGEROUS"  # reserved — no tool uses this yet


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tier: PermissionTier
    description: str
    dispatch: Callable[[Any], bool]  # (action_param) -> True if it actually ran


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


def build_default_registry(action_manager, memory_manager) -> ToolRegistry:
    """Registers the tools CompanionOrchestrator._execute_action used to dispatch
    by hand. Each dispatch guard reproduces that method's original truthiness/shape
    checks exactly, so wiring this in changes nothing about what executes — only
    how it's looked up and what permission tier it's tagged with."""
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="open_application",
        tier=PermissionTier.CONFIRM,
        description="Abre um aplicativo da allowlist.",
        dispatch=lambda param: _open_application(action_manager, param),
    ))
    registry.register(ToolSpec(
        name="open_url",
        tier=PermissionTier.CONFIRM,
        description="Abre uma URL no navegador padrão.",
        dispatch=lambda param: _open_url(action_manager, param),
    ))
    registry.register(ToolSpec(
        name="search_web",
        tier=PermissionTier.SAFE,
        description="Pesquisa um termo na web.",
        dispatch=lambda param: _search_web(action_manager, param),
    ))
    registry.register(ToolSpec(
        name="remember",
        tier=PermissionTier.SAFE,
        description="Salva uma informação na memória de longo prazo.",
        dispatch=lambda param: _remember(memory_manager, param),
    ))
    registry.register(ToolSpec(
        name="forget_memory",
        tier=PermissionTier.SAFE,
        description="Remove uma informação da memória.",
        dispatch=lambda param: _forget_memory(memory_manager, param),
    ))
    return registry
