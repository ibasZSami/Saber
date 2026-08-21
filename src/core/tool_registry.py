import time
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
        "description": (
            "Abre um aplicativo pelo nome (ex: chrome, discord, vscode, firefox, spotify). "
            "Não precisa estar pré-cadastrado — se não estiver na allowlist, tenta resolver "
            "automaticamente qualquer app já instalado no Windows."
        ),
        "parameters": {"application": "string"},
    },
    {
        "name": "close_application",
        "tier": PermissionTier.CONFIRM,
        "description": "Fecha um aplicativo configurado na allowlist (ex: chrome, discord, vscode).",
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
    {
        "name": "set_app_volume",
        "tier": PermissionTier.CONFIRM,
        "description": "Ajusta o volume de um aplicativo específico no mixer de som do Windows (0 a 100).",
        "parameters": {"application": "string", "level": "number (0-100)"},
    },
    {
        "name": "research_topic",
        "tier": PermissionTier.SAFE,
        "description": "Inicia uma pesquisa real na web em segundo plano sobre um tópico e avisa quando terminar — não bloqueia a conversa.",
        "parameters": {"query": "string"},
    },
    {
        "name": "create_reminder",
        "tier": PermissionTier.SAFE,
        "description": "Agenda um lembrete/timer — anuncia a mensagem em voz alta quando o tempo passar.",
        "parameters": {"message": "string", "minutes_from_now": "number"},
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


# A malformed/hallucinated AI response could hand any JSON-decodable shape
# (a dict, a list, a number, True/False) as action_param instead of the
# string these tools expect — `dict.lower()`/similar calls further down the
# chain (DesktopActionManager, sqlite params) raise on the wrong type instead
# of failing cleanly. Checking the type here, not just truthiness, turns that
# into an ordinary "not handled" instead of an uncaught exception escaping
# the dispatch call.


def _open_application(action_manager, action_param) -> bool:
    if not isinstance(action_param, str) or not action_param.strip():
        return False
    return bool(action_manager.open_application(action_param))


def _close_application(action_manager, action_param) -> bool:
    if not isinstance(action_param, str) or not action_param.strip():
        return False
    return bool(action_manager.close_application(action_param))


def _open_url(action_manager, action_param) -> bool:
    if not isinstance(action_param, str) or not action_param.strip():
        return False
    return bool(action_manager.open_url(action_param))


def _search_web(action_manager, action_param) -> bool:
    if not isinstance(action_param, str) or not action_param.strip():
        return False
    return bool(action_manager.search_web(action_param))


def _remember(memory_manager, action_param) -> bool:
    if not isinstance(action_param, dict):
        return False
    key = action_param.get("key")
    if not isinstance(key, str) or not key.strip():
        return False
    memory_manager.remember(key, action_param.get("value", ""))
    return True


def _forget_memory(memory_manager, action_param) -> bool:
    key = action_param.get("key") if isinstance(action_param, dict) else action_param
    if not isinstance(key, str) or not key.strip():
        return False
    memory_manager.forget(key)
    return True


def _set_app_volume(audio_mixer_manager, action_param) -> bool:
    if not isinstance(action_param, dict):
        return False
    app = action_param.get("application")
    level = action_param.get("level")
    if not isinstance(app, str) or not app.strip() or level is None:
        return False
    try:
        level = float(level)
    except (TypeError, ValueError):
        return False
    # Clamp rather than reject out-of-range values — an AI-hallucinated
    # level of 500 (or a negative one) must not reach the OS mixer as-is;
    # pycaw's SetVolumeScalar has no defined behavior for a scalar outside
    # [0.0, 1.0].
    level = max(0.0, min(100.0, level))
    return bool(audio_mixer_manager.set_volume(app, level / 100.0))


def _research_topic(background_task_manager, research_manager, action_param) -> bool:
    if not action_param or not str(action_param).strip():
        return False
    query = str(action_param).strip()
    background_task_manager.create_task("research", query, lambda: research_manager.research(query))
    return True


def _create_reminder(scheduler, action_param) -> bool:
    if not isinstance(action_param, dict):
        return False
    message = action_param.get("message")
    if not isinstance(message, str) or not message.strip():
        return False
    try:
        minutes = float(action_param.get("minutes_from_now"))
    except (TypeError, ValueError):
        return False
    if minutes <= 0:
        return False
    scheduler.create(message.strip(), time.time() + minutes * 60)
    return True


# Tool names with a real dispatch handler — observe_screen/translate_screen are
# deliberately absent (see _TOOL_DEFS' comment above).
_DISPATCH_BUILDERS = {
    "open_application": lambda m: (lambda p: _open_application(m["action_manager"], p)),
    "close_application": lambda m: (lambda p: _close_application(m["action_manager"], p)),
    "open_url": lambda m: (lambda p: _open_url(m["action_manager"], p)),
    "search_web": lambda m: (lambda p: _search_web(m["action_manager"], p)),
    "remember": lambda m: (lambda p: _remember(m["memory_manager"], p)),
    "forget_memory": lambda m: (lambda p: _forget_memory(m["memory_manager"], p)),
    "set_app_volume": lambda m: (lambda p: _set_app_volume(m["audio_mixer_manager"], p)),
    "research_topic": lambda m: (lambda p: _research_topic(m["background_task_manager"], m["research_manager"], p)),
    "create_reminder": lambda m: (lambda p: _create_reminder(m["scheduler"], p)),
}


def build_default_registry(
    action_manager,
    memory_manager,
    audio_mixer_manager=None,
    background_task_manager=None,
    research_manager=None,
    scheduler=None,
) -> ToolRegistry:
    """Registers every tool from _TOOL_DEFS, binding a real dispatch handler for
    the ones that have one. Each dispatch guard reproduces the original
    CompanionOrchestrator._execute_action if/elif's truthiness/shape checks
    exactly, so wiring this in changes nothing about what executes — only how
    it's looked up and what permission tier it's tagged with.

    audio_mixer_manager is optional (defaults to a fresh AudioMixerManager) so
    existing callers that only pass the first two managers keep working.
    background_task_manager/research_manager have no sensible zero-arg default
    (a real ResearchManager needs an AI provider) — if either is omitted,
    research_topic stays descriptive-only (no dispatch), same as
    observe_screen/translate_screen. scheduler works the same way for
    create_reminder — it needs a real Database-backed instance, no default."""
    if audio_mixer_manager is None:
        from src.desktop.audio_mixer import AudioMixerManager
        audio_mixer_manager = AudioMixerManager()
    managers = {
        "action_manager": action_manager,
        "memory_manager": memory_manager,
        "audio_mixer_manager": audio_mixer_manager,
        "background_task_manager": background_task_manager,
        "research_manager": research_manager,
        "scheduler": scheduler,
    }
    registry = ToolRegistry()
    for tool_def in _TOOL_DEFS:
        name = tool_def["name"]
        build_dispatch = _DISPATCH_BUILDERS.get(name)
        research_deps_missing = name == "research_topic" and (
            background_task_manager is None or research_manager is None
        )
        reminder_deps_missing = name == "create_reminder" and scheduler is None
        dispatch = (
            build_dispatch(managers)
            if build_dispatch and not research_deps_missing and not reminder_deps_missing
            else None
        )
        registry.register(ToolSpec(
            name=name,
            tier=tool_def["tier"],
            description=tool_def["description"],
            dispatch=dispatch,
            parameters=tool_def.get("parameters"),
        ))
    return registry
