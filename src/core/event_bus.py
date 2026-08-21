import logging
from collections import defaultdict
from typing import Callable, Any

from PySide6.QtCore import QObject, Signal


class _Dispatcher(QObject):
    """The only piece of EventBus that touches Qt. A single generic signal
    fans out to every subscriber for every event type. Connected with Qt's
    default Qt.AutoConnection, which resolves per-emit: if emit() is called
    from the same thread that constructed this dispatcher (always the GUI
    thread in practice — EventBus is built inside CompanionOrchestrator on
    the main thread), the slot runs immediately/synchronously, identical to
    the old plain-Python behavior. If emit() is called from any other thread
    (a background worker — spontaneous speech, background tasks, CONFIRM
    permission checks), Qt automatically queues the call onto the
    dispatcher's own (GUI) thread instead of running it in place.

    That's the actual fix for FASE 3: a subscriber can safely update a Qt
    widget without knowing or caring what thread emitted the event — the
    same guarantee that already made animation_manager.py's frame_changed
    signal safe (see FASE 0 audit), now generic to every EventBus event
    instead of needing a bespoke Signal/QueuedConnection per case (as
    chat_window.py's append_message needed before this)."""

    _fire = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.subscribers = defaultdict(list)
        self._fire.connect(self._dispatch)

    def _dispatch(self, event_type: str, kwargs: dict):
        for callback in list(self.subscribers[event_type]):
            try:
                callback(**kwargs)
            except Exception as e:
                logging.error(f"Error executing callback for event {event_type}: {e}", exc_info=True)


class EventBus:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._instance._dispatcher = _Dispatcher()
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable[..., Any]):
        subs = self._dispatcher.subscribers[event_type]
        if callback not in subs:
            subs.append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[..., Any]):
        subs = self._dispatcher.subscribers[event_type]
        if callback in subs:
            subs.remove(callback)

    def emit(self, event_type: str, **kwargs):
        logging.debug(f"EventBus emit: {event_type} - args: {kwargs}")
        self._dispatcher._fire.emit(event_type, kwargs)

    def reset(self):
        """Clears every subscriber. EventBus is a process-wide singleton, so
        without this, subscribers registered by one test/session accumulate
        forever and leak into unrelated later ones — see tests/conftest.py,
        which calls this before and after every test. Not used in production
        (the app never wants to forget its own subscribers mid-run)."""
        self._dispatcher.subscribers.clear()

# Common Event Names
SCREEN_CHANGED = "SCREEN_CHANGED"
APPLICATION_CHANGED = "APPLICATION_CHANGED"
GAME_STARTED = "GAME_STARTED"
GAME_ENDED = "GAME_ENDED"
USER_SPOKE = "USER_SPOKE"
AI_STARTED = "AI_STARTED"
AI_FINISHED = "AI_FINISHED"
VOICE_STARTED = "VOICE_STARTED"
VOICE_FINISHED = "VOICE_FINISHED"
TRANSLATION_REQUESTED = "TRANSLATION_REQUESTED"
USER_CLICKED_CHARACTER = "USER_CLICKED_CHARACTER"
WINDOW_CHANGED = "WINDOW_CHANGED"
IDLE_TIMEOUT = "IDLE_TIMEOUT"
ERROR_OCCURRED = "ERROR_OCCURRED"
STATE_CHANGED = "STATE_CHANGED"

# Added in the Silva Core / Event Bus adoption pass (see plan doc for context)
VISION_REQUESTED = "VISION_REQUESTED"
VISION_RESULT = "VISION_RESULT"
SYSTEM_AUDIO_DETECTED = "SYSTEM_AUDIO_DETECTED"
MEMORY_CREATED = "MEMORY_CREATED"
MEMORY_RECALLED = "MEMORY_RECALLED"
ACTION_REQUESTED = "ACTION_REQUESTED"
ACTION_EXECUTED = "ACTION_EXECUTED"
ACTION_REJECTED = "ACTION_REJECTED"
EMOTION_CHANGED = "EMOTION_CHANGED"
CHARACTER_STATE_CHANGED = "CHARACTER_STATE_CHANGED"
SPONTANEOUS_SPEECH = "SPONTANEOUS_SPEECH"

# Fired when a CONFIRM-tier tool executes without an actual confirmation prompt
# (no UI for that exists yet) — lets a future dialog intercept at one seam later,
# and gives today's logs a distinct signal from a plain SAFE-tier execution.
ACTION_CONFIRM_AUTO_APPROVED = "ACTION_CONFIRM_AUTO_APPROVED"

# NERD MODE toggle (kwargs: enabled: bool)
NERD_MODE_TOGGLED = "NERD_MODE_TOGGLED"

# Fired when open_application resolves an app outside the allowlist on the fly
# (see src/desktop/app_resolver.py) — kwargs: app_name: str, command: str. NOT
# persisted to the allowlist automatically; this just lets the UI tell the user
# it happened, since silently launching an unrecognized app name deserves at
# least a visible notice even though it isn't remembered.
APP_AUTO_RESOLVED = "APP_AUTO_RESOLVED"

# Screen Vision toggle (kwargs: enabled: bool) — covers the "-" hotkey, tray menu,
# and "minha tela" voice/text command, all of which call set_full_vision() directly
# instead of going through handle_user_message, so they had no user-visible
# confirmation before this event existed.
VISION_MONITORING_TOGGLED = "VISION_MONITORING_TOGGLED"

# Background task lifecycle (see src/core/background_tasks.py). kwargs always
# include task_id; COMPLETED also includes result, FAILED includes error.
TASK_STARTED = "TASK_STARTED"
TASK_COMPLETED = "TASK_COMPLETED"
TASK_FAILED = "TASK_FAILED"

# Real CONFIRM-tier flow (see src/core/agent_core.py, src/ui/confirmation_dialog.py).
# kwargs: action: str, action_param, and (REQUESTED only) description: str — the
# human-readable text shown in the dialog. Fired only when AgentCore was built
# with a real confirm_fn; when none is wired (background/legacy paths),
# ACTION_CONFIRM_AUTO_APPROVED above still fires instead, unchanged.
PERMISSION_REQUESTED = "PERMISSION_REQUESTED"
PERMISSION_GRANTED = "PERMISSION_GRANTED"
PERMISSION_DENIED = "PERMISSION_DENIED"

# Scheduler (FASE 12) — kwargs: reminder_id: int, message: str, and
# (CREATED only) fire_at: float (unix timestamp).
REMINDER_CREATED = "REMINDER_CREATED"
REMINDER_FIRED = "REMINDER_FIRED"

# Agent Engine task loop (see src/core/agent_engine.py, src/core/task_manager.py).
# All kwargs include task_id: str. STARTED also has goal: str; STEP has
# action, action_param, observation, step_number; COMPLETED has result: str;
# FAILED has error: str. Deliberately separate names from
# TASK_STARTED/COMPLETED/FAILED above (BackgroundTaskManager's single-shot
# fire-and-forget work) — a multi-step agent task is a different lifecycle
# (pausable, has a step history) and conflating the two event streams would
# make either one impossible to listen to cleanly on its own.
TASK_LOOP_STARTED = "TASK_LOOP_STARTED"
TASK_LOOP_STEP = "TASK_LOOP_STEP"
TASK_LOOP_PAUSED = "TASK_LOOP_PAUSED"
TASK_LOOP_RESUMED = "TASK_LOOP_RESUMED"
TASK_LOOP_CANCELLED = "TASK_LOOP_CANCELLED"
TASK_LOOP_COMPLETED = "TASK_LOOP_COMPLETED"
TASK_LOOP_FAILED = "TASK_LOOP_FAILED"
