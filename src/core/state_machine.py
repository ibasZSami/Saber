import logging
from src.core.event_bus import EventBus, STATE_CHANGED

class StateMachine:
    def __init__(self, initial_state: str = "IDLE"):
        self.current_state = initial_state
        self.event_bus = EventBus()
        self.previous_state = initial_state

    def get_state(self) -> str:
        return self.current_state

    def transition_to(self, new_state: str, reason: str = ""):
        if self.current_state == new_state:
            return

        self.previous_state = self.current_state
        self.current_state = new_state
        logging.info(f"State transition: {self.previous_state} -> {self.current_state} (Reason: {reason})")
        self.event_bus.emit(STATE_CHANGED, old_state=self.previous_state, new_state=self.current_state, reason=reason)

    def revert(self):
        if self.previous_state:
            self.transition_to(self.previous_state, reason="Revert to previous state")
