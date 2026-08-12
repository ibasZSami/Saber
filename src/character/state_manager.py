import logging
from src.core.state_machine import StateMachine
from src.core.event_bus import CHARACTER_STATE_CHANGED
from src.character.animation_manager import AnimationManager

STATE_ANIM_MAP = {
    "IDLE": "idle",
    "WALK": "walk",
    "RUN": "run",
    "THINKING": "thinking",
    "TALKING": "talking",
    "LISTENING": "interaction",
    "HAPPY": "happy",
    "SAD": "sad",
    "ANGRY": "angry",
    "SURPRISED": "surprised",
    "CONFUSED": "confused",
    "SHY": "shy",
    "SERIOUS": "serious",
    "BRAVE": "brave",
    "SLEEP": "sleep",
    "EAT": "eat",
    "EXCITED": "excited",
    "DRINK": "drink",
    "READ": "read",
    "WORKING": "work_pc",
    "GAMING": "game",
    "INTERACTION": "interaction",
    "DEFEND": "defend",
    "ATTACK": "attack_basic",
    "HURT": "hurt",
    "DEATH": "death",
    "TELEPORT": "teleport_in",
    # No dedicated sprite — reuses "serious" as a discreet visual cue that
    # NERD MODE is on, rather than adding new art for it.
    "NERD_ACTIVE": "serious",
}

class CharacterStateManager:
    def __init__(self, state_machine: StateMachine, animation_manager: AnimationManager):
        self.state_machine = state_machine
        self.animation_manager = animation_manager
        self.state_machine.event_bus.subscribe("STATE_CHANGED", self._on_state_changed)

    def _on_state_changed(self, old_state: str, new_state: str, reason: str = ""):
        anim_name = STATE_ANIM_MAP.get(new_state.upper(), "idle")
        self.animation_manager.play(anim_name)
        self.state_machine.event_bus.emit(CHARACTER_STATE_CHANGED, state=new_state, animation=anim_name, reason=reason)

    def set_state(self, state_name: str, reason: str = ""):
        self.state_machine.transition_to(state_name.upper(), reason=reason)
