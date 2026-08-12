import logging
from collections import defaultdict
from typing import Callable, Any

class EventBus:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._instance._subscribers = defaultdict(list)
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable[..., Any]):
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[..., Any]):
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)

    def emit(self, event_type: str, **kwargs):
        logging.debug(f"EventBus emit: {event_type} - args: {kwargs}")
        for callback in list(self._subscribers[event_type]):
            try:
                callback(**kwargs)
            except Exception as e:
                logging.error(f"Error executing callback for event {event_type}: {e}", exc_info=True)

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
