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

    def as_tools_schema(self, dispatchable_only: bool = False) -> List[Dict[str, Any]]:
        """Rebuilds the prompt-facing {name, description, parameters} shape from
        the registered specs, so the AI-facing schema and the dispatch table can't
        drift apart the way two hand-kept-in-sync lists eventually would.

        dispatchable_only=True filters out any tool with no real dispatch
        handler wired (spec.dispatch is None) — used by the Agent Engine
        (src/core/agent_engine.py), which unlike the conversational prompt
        has no use for "descriptive only, triggered elsewhere" tools like
        observe_screen, or a tool gated off by a Settings master switch (see
        build_default_registry): every entry it's told about must actually
        be something it can try."""
        schema = []
        for spec in self._tools.values():
            if dispatchable_only and spec.dispatch is None:
                continue
            entry = {"name": spec.name, "description": spec.description}
            if spec.parameters:
                entry["parameters"] = spec.parameters
            schema.append(entry)
        return schema


# Static metadata for every tool the AI can be told about. translate_screen
# stays descriptive-only (the one-shot "Traduz isso" flow is keyword-
# triggered in orchestrator.py, not a clean fit for this dispatch table) —
# but observe_screen (FASE 8) DOES have a real dispatch now: a pure OCR
# read of the current screen, so the Agent Engine's task loop can actually
# "look" at something mid-task instead of only reacting to chat keywords.
_TOOL_DEFS = [
    {
        "name": "observe_screen",
        "tier": PermissionTier.SAFE,
        "description": "Lê o texto visível na tela agora (OCR) — usa isso pra ver o que está escrito antes de decidir o próximo passo de uma tarefa.",
    },
    {
        "name": "translate_screen",
        "tier": PermissionTier.SAFE,
        "description": "Captura a tela, executa OCR e traduz o texto selecionado.",
    },
    {
        "name": "activate_translation_mode",
        "tier": PermissionTier.SAFE,
        "description": "Liga o modo de tradução contínua da tela (overlay traduzindo em tempo real) — equivalente ao comando de voz \"traduzir\".",
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
    {
        "name": "mouse_click",
        "tier": PermissionTier.CONFIRM,
        "description": "Move o mouse até (x, y) na tela e clica. Coordenadas em pixels, origem no canto superior esquerdo.",
        "parameters": {"x": "number", "y": "number", "button": '"left" ou "right" (padrão left)'},
    },
    {
        "name": "mouse_move",
        "tier": PermissionTier.CONFIRM,
        "description": "Move o mouse até (x, y) na tela, sem clicar.",
        "parameters": {"x": "number", "y": "number"},
    },
    {
        "name": "type_text",
        "tier": PermissionTier.CONFIRM,
        "description": "Digita um texto na posição atual do cursor/foco, como se fosse teclado real.",
        "parameters": {"text": "string"},
    },
    {
        "name": "press_key",
        "tier": PermissionTier.CONFIRM,
        "description": (
            "Pressiona uma tecla especial (enter, tab, esc, backspace, delete, space, "
            "up/down/left/right, home, end, pageup, pagedown) ou um único caractere."
        ),
        "parameters": {"key": "string"},
    },
    {
        "name": "run_terminal_tool",
        "tier": PermissionTier.CONFIRM,
        "description": (
            "Executa um binário pré-aprovado da allowlist de terminal (Configurações → Terminal) "
            "com argumentos — nunca um comando de shell livre, e nada roda se não estiver na allowlist."
        ),
        "parameters": {"name": "string", "args": "string (opcional)"},
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


def _to_coordinate(value) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if not (0 <= n <= 10000):
        return None
    return n


def _mouse_click(input_controller, action_param) -> bool:
    if not isinstance(action_param, dict):
        return False
    x, y = _to_coordinate(action_param.get("x")), _to_coordinate(action_param.get("y"))
    if x is None or y is None:
        return False
    button = action_param.get("button", "left")
    button = button if button in ("left", "right") else "left"
    return input_controller.click(x, y, button=button)


def _mouse_move(input_controller, action_param) -> bool:
    if not isinstance(action_param, dict):
        return False
    x, y = _to_coordinate(action_param.get("x")), _to_coordinate(action_param.get("y"))
    if x is None or y is None:
        return False
    return input_controller.move(x, y)


def _type_text(input_controller, action_param) -> bool:
    text = action_param.get("text") if isinstance(action_param, dict) else action_param
    if not isinstance(text, str) or not text:
        return False
    return input_controller.type_text(text)


def _press_key(input_controller, action_param) -> bool:
    key = action_param.get("key") if isinstance(action_param, dict) else action_param
    if not isinstance(key, str) or not key.strip():
        return False
    return input_controller.press_key(key.strip())


def _run_terminal_tool(terminal_tool_manager, action_param):
    if not isinstance(action_param, dict):
        return False, None
    name = action_param.get("name")
    if not isinstance(name, str) or not name.strip():
        return False, None
    args = action_param.get("args", "")
    if not isinstance(args, str):
        args = ""
    result = terminal_tool_manager.run(name, args)
    # detail is the real command output on success, or the refusal/error
    # reason on failure — either way, worth surfacing to whatever's reading
    # execute_with_detail() (the Agent Engine task loop, FASE 8), not just
    # a bare bool.
    detail = result.get("output") if result.get("success") else result.get("error")
    return bool(result.get("success")), detail


def _observe_screen(screen_capture, ocr_provider, action_param):
    """FASE 8 — a real, dispatchable "look at the screen" for the Agent
    Engine's task loop (chat's own vision path stays keyword-triggered,
    unaffected — see _TOOL_DEFS' comment). Pure OCR text read, not an
    AI-vision image description — cheaper, faster, and enough for a task
    loop to react to on-screen text (dialog boxes, menu labels, HUD text)."""
    try:
        img = screen_capture.capture_primary()
        result = ocr_provider.extract_text(img)
    except Exception as e:
        return False, str(e)
    text = result.get("text", "")
    if not text:
        return False, result.get("error") or "Nenhum texto legível encontrado na tela."
    return True, text


def _activate_translation_mode(translation_mode, action_param) -> bool:
    translation_mode.start()
    return True


# Tool names with a real dispatch handler — translate_screen is
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
    "mouse_click": lambda m: (lambda p: _mouse_click(m["input_controller"], p)),
    "mouse_move": lambda m: (lambda p: _mouse_move(m["input_controller"], p)),
    "type_text": lambda m: (lambda p: _type_text(m["input_controller"], p)),
    "press_key": lambda m: (lambda p: _press_key(m["input_controller"], p)),
    "run_terminal_tool": lambda m: (lambda p: _run_terminal_tool(m["terminal_tool_manager"], p)),
    "observe_screen": lambda m: (lambda p: _observe_screen(m["screen_capture"], m["ocr_provider"], p)),
    "activate_translation_mode": lambda m: (lambda p: _activate_translation_mode(m["translation_mode"], p)),
}


def build_default_registry(
    action_manager,
    memory_manager,
    audio_mixer_manager=None,
    background_task_manager=None,
    research_manager=None,
    scheduler=None,
    input_controller=None,
    terminal_tool_manager=None,
    screen_capture=None,
    ocr_provider=None,
    translation_mode=None,
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
    create_reminder — it needs a real Database-backed instance, no default.

    input_controller/terminal_tool_manager follow the same "no dispatch
    without a real instance" rule — and orchestrator.py deliberately never
    constructs one unless the matching Settings master switch
    (input_control_enabled / terminal_tool_enabled) is on, so these tools
    stay entirely unregistered — not just unconfirmed, genuinely absent from
    what the AI is even told exists — until a user opts in. See FASE 3.

    screen_capture+ocr_provider (both needed together) enable observe_screen's
    real dispatch; translation_mode enables activate_translation_mode's — see
    FASE 8."""
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
        "input_controller": input_controller,
        "terminal_tool_manager": terminal_tool_manager,
        "screen_capture": screen_capture,
        "ocr_provider": ocr_provider,
        "translation_mode": translation_mode,
    }
    registry = ToolRegistry()
    for tool_def in _TOOL_DEFS:
        name = tool_def["name"]
        build_dispatch = _DISPATCH_BUILDERS.get(name)
        research_deps_missing = name == "research_topic" and (
            background_task_manager is None or research_manager is None
        )
        reminder_deps_missing = name == "create_reminder" and scheduler is None
        input_deps_missing = name in ("mouse_click", "mouse_move", "type_text", "press_key") and (
            input_controller is None
        )
        terminal_deps_missing = name == "run_terminal_tool" and terminal_tool_manager is None
        observe_deps_missing = name == "observe_screen" and (screen_capture is None or ocr_provider is None)
        translation_mode_deps_missing = name == "activate_translation_mode" and translation_mode is None
        deps_missing = (
            research_deps_missing or reminder_deps_missing or input_deps_missing or terminal_deps_missing
            or observe_deps_missing or translation_mode_deps_missing
        )
        dispatch = build_dispatch(managers) if build_dispatch and not deps_missing else None
        registry.register(ToolSpec(
            name=name,
            tier=tool_def["tier"],
            description=tool_def["description"],
            dispatch=dispatch,
            parameters=tool_def.get("parameters"),
        ))
    return registry
