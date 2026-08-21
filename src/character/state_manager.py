from typing import Optional

from src.core.state_machine import StateMachine
from src.core.event_bus import CHARACTER_STATE_CHANGED, EMOTION_CHANGED
from src.character.animation_manager import AnimationManager

# Functional state — what Silva is actually DOING right now, driven only by
# system/orchestrator logic (voice input, screen/game detection, background
# behavior), never by the AI's free text choice. See set_state().
STATE_ANIM_MAP = {
    "IDLE": "idle",
    "WALK": "walk",
    "RUN": "run",
    "THINKING": "thinking",
    "TALKING": "talking",
    "LISTENING": "interaction",
    "WORKING": "work_pc",
    "GAMING": "game",
    "INTERACTION": "interaction",
    "SLEEP": "sleep",
    # No dedicated sprite — reuses "serious" as a discreet visual cue that
    # NERD MODE is on, rather than adding new art for it.
    "NERD_ACTIVE": "serious",
}

# Emotion — how Silva feels, chosen by the AI's "emotion" field in its JSON
# reply (see src/ai/tools.py, src/ai/prompts.py) or by a deterministic
# system reaction (a failed voice command, an internal error). Independent
# axis from functional state — see set_emotion().
EMOTION_ANIM_MAP = {
    "HAPPY": "happy",
    "SAD": "sad",
    "ANGRY": "angry",
    "SURPRISED": "surprised",
    "CONFUSED": "confused",
    "SHY": "shy",
    "SERIOUS": "serious",
    "BRAVE": "brave",
    "EXCITED": "excited",
    "EAT": "eat",
    "DRINK": "drink",
    "READ": "read",
    "DEFEND": "defend",
    "ATTACK": "attack_basic",
    "HURT": "hurt",
    "DEATH": "death",
    "TELEPORT": "teleport_in",
}

# Functional states in which an active emotion is actually shown, instead of
# the plain functional sprite — this is where FASE 13 differs from the old
# single-track design. Silva "looking happy" only makes visual sense when
# she isn't otherwise busy: GAMING/THINKING/WORKING/etc keep their own
# sprite (no art combines "gaming + happy"), and the emotion is simply
# remembered, re-applied automatically the next time she returns to IDLE or
# TALKING — it's never lost, just not shown while something else has visual
# priority.
EMOTION_VISIBLE_STATES = {"IDLE", "TALKING"}


class CharacterStateManager:
    def __init__(self, state_machine: StateMachine, animation_manager: AnimationManager):
        self.state_machine = state_machine
        self.animation_manager = animation_manager
        self._current_emotion: Optional[str] = None
        self.state_machine.event_bus.subscribe("STATE_CHANGED", self._on_state_changed)

    def _on_state_changed(self, old_state: str, new_state: str, reason: str = ""):
        self._render(new_state, reason)

    def _render(self, functional_state: str, reason: str):
        upper = functional_state.upper()
        if upper in EMOTION_VISIBLE_STATES and self._current_emotion:
            anim_name = EMOTION_ANIM_MAP.get(self._current_emotion, STATE_ANIM_MAP.get(upper, "idle"))
        else:
            anim_name = STATE_ANIM_MAP.get(upper, "idle")
        self.animation_manager.play(anim_name)
        self.state_machine.event_bus.emit(CHARACTER_STATE_CHANGED, state=upper, animation=anim_name, reason=reason)

    def set_state(self, state_name: str, reason: str = ""):
        self.state_machine.transition_to(state_name.upper(), reason=reason)

    def set_emotion(self, emotion_name: Optional[str], reason: str = ""):
        """The AI-driven (or deterministic-reaction) expressive layer,
        independent of functional state. Renders immediately if the current
        functional state is neutral (see EMOTION_VISIBLE_STATES); otherwise
        stored silently and applied automatically next time Silva returns to
        a neutral state. Pass None (or an unrecognized name) to clear it."""
        normalized = emotion_name.upper() if emotion_name else None
        if normalized not in EMOTION_ANIM_MAP:
            normalized = None
        self._current_emotion = normalized
        self.state_machine.event_bus.emit(EMOTION_CHANGED, emotion=normalized, reason=reason)
        self._render(self.state_machine.get_state(), reason)
