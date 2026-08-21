"""Friendly, human-readable action history ("o que a Silva fez") — FASE 7.
Subscribes to the same EventBus every other subsystem already emits on, so a
future loggable action is one more subscribe() call, not new plumbing.

Deliberately curated, not exhaustive: MEMORY_RECALLED fires on nearly every
turn, WINDOW_CHANGED on every window switch — both are internal noise, not
"activity" a user would recognize. Only actions with real user-facing meaning
are logged."""

import time
from collections import deque
from dataclasses import dataclass

from src.core.event_bus import (
    EventBus,
    ACTION_EXECUTED, ACTION_REJECTED, ACTION_CONFIRM_AUTO_APPROVED,
    APP_AUTO_RESOLVED, MEMORY_CREATED,
    NERD_MODE_TOGGLED, VISION_MONITORING_TOGGLED,
    TASK_COMPLETED, TASK_FAILED, ERROR_OCCURRED,
    REMINDER_CREATED, REMINDER_FIRED,
    TRANSLATION_MODE_STATE_CHANGED,
)

MAX_ENTRIES = 200


@dataclass(frozen=True)
class ActivityEntry:
    timestamp: float
    text: str


def _describe_action_result(action, action_param, rejected: bool) -> str:
    if action == "open_application":
        return f'{"Não conseguiu abrir" if rejected else "Abriu"} o aplicativo "{action_param}".'
    if action == "close_application":
        return f'{"Não conseguiu fechar" if rejected else "Fechou"} o aplicativo "{action_param}".'
    if action == "open_url":
        return "Não abriu a página." if rejected else "Abriu uma página no navegador."
    if action == "search_web":
        return f'{"Não pesquisou" if rejected else "Pesquisou"} na web: "{action_param}".'
    if action == "set_app_volume":
        app = action_param.get("application", "?") if isinstance(action_param, dict) else "?"
        level = action_param.get("level", "?") if isinstance(action_param, dict) else "?"
        return f'{"Não ajustou" if rejected else "Ajustou"} o volume de "{app}" para {level}%.'
    if action in ("mouse_click", "mouse_move", "type_text", "press_key"):
        return f'{"Não controlou" if rejected else "Controlou"} o mouse/teclado ({action}).'
    if action == "run_terminal_tool":
        name = action_param.get("name", "?") if isinstance(action_param, dict) else "?"
        return f'{"Não rodou" if rejected else "Rodou"} "{name}" no terminal.'
    if action == "browser_navigate":
        url = action_param.get("url", "?") if isinstance(action_param, dict) else action_param
        return f'{"Não abriu" if rejected else "Abriu"} "{url}" no navegador controlado.'
    if action in ("browser_click", "browser_type"):
        return f'{"Não controlou" if rejected else "Controlou"} o navegador ({action}).'
    return f'{"Não executou" if rejected else "Executou"} a ação "{action}".'


class ActivityLog:
    """Keeps the last MAX_ENTRIES loggable actions in memory only — not
    persisted to disk, same lifetime as the app process. A history that
    outlived restarts would need its own retention/privacy policy (what to
    purge, for how long); in-memory keeps this FASE 7 addition simple and
    matches what "Diagnóstico" already does with its report."""

    def __init__(self, event_bus: EventBus = None):
        self.event_bus = event_bus or EventBus()
        self._entries = deque(maxlen=MAX_ENTRIES)
        self.event_bus.subscribe(ACTION_EXECUTED, self._on_action_executed)
        self.event_bus.subscribe(ACTION_REJECTED, self._on_action_rejected)
        self.event_bus.subscribe(ACTION_CONFIRM_AUTO_APPROVED, self._on_action_executed)
        self.event_bus.subscribe(APP_AUTO_RESOLVED, self._on_app_auto_resolved)
        self.event_bus.subscribe(MEMORY_CREATED, self._on_memory_created)
        self.event_bus.subscribe(NERD_MODE_TOGGLED, self._on_nerd_mode_toggled)
        self.event_bus.subscribe(VISION_MONITORING_TOGGLED, self._on_vision_toggled)
        self.event_bus.subscribe(TASK_COMPLETED, self._on_task_completed)
        self.event_bus.subscribe(TASK_FAILED, self._on_task_failed)
        self.event_bus.subscribe(ERROR_OCCURRED, self._on_error)
        self.event_bus.subscribe(REMINDER_CREATED, self._on_reminder_created)
        self.event_bus.subscribe(REMINDER_FIRED, self._on_reminder_fired)
        self.event_bus.subscribe(TRANSLATION_MODE_STATE_CHANGED, self._on_translation_mode_state_changed)

    def _add(self, text: str):
        self._entries.append(ActivityEntry(timestamp=time.time(), text=text))

    def _on_action_executed(self, action, action_param):
        self._add(_describe_action_result(action, action_param, rejected=False))

    def _on_action_rejected(self, action, action_param):
        self._add(_describe_action_result(action, action_param, rejected=True))

    def _on_app_auto_resolved(self, app_name, command):
        self._add(f'Abriu "{app_name}" (fora da lista de aplicativos configurados).')

    def _on_memory_created(self, key, value):
        self._add(f'Guardou uma memória: "{key}".')

    def _on_nerd_mode_toggled(self, enabled):
        self._add("Modo Nerd ativado." if enabled else "Modo Nerd desativado.")

    def _on_vision_toggled(self, enabled):
        self._add("Visão de tela ativada." if enabled else "Visão de tela desativada.")

    def _on_task_completed(self, task_id, task_type, description, result):
        self._add(f"Concluiu: {description}.")

    def _on_task_failed(self, task_id, task_type, description, error):
        self._add(f"Não conseguiu concluir: {description}.")

    def _on_error(self, source, error):
        self._add(f"Ocorreu um erro em {source}.")

    def _on_reminder_created(self, reminder_id, message, fire_at):
        self._add(f'Agendou um lembrete: "{message}".')

    def _on_reminder_fired(self, reminder_id, message):
        self._add(f'Avisou um lembrete: "{message}".')

    def _on_translation_mode_state_changed(self, state):
        # STARTING/STOPPING are transient mid-flight states — only the
        # settled RUNNING/OFF endpoints are worth a log line.
        if state == "RUNNING":
            self._add("Ativou o modo de tradução contínua da tela.")
        elif state == "OFF":
            self._add("Desativou o modo de tradução contínua da tela.")

    def entries(self):
        return list(self._entries)

    def clear(self):
        self._entries.clear()


def format_activity_log(entries) -> str:
    """Plain text, safe to show in a UI text box — see settings_window.py's
    Atividade tab. Newest first, so the user sees what just happened without
    scrolling."""
    if not entries:
        return "Nenhuma atividade registrada ainda."
    lines = []
    for entry in reversed(entries):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        lines.append(f"[{ts}] {entry.text}")
    return "\n".join(lines)
