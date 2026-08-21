from unittest.mock import MagicMock

from src.character.state_manager import CharacterStateManager
from src.core.state_machine import StateMachine


class TestFunctionalState:
    def test_set_state_uppercases_and_delegates(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)

        char_mgr.set_state("talking", reason="teste")

        assert sm.get_state() == "TALKING"

    def test_state_change_triggers_mapped_animation(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        CharacterStateManager(sm, anim_mgr)

        sm.transition_to("TALKING")

        anim_mgr.play.assert_called_with("talking")

    def test_unknown_state_falls_back_to_idle_animation(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        CharacterStateManager(sm, anim_mgr)

        sm.transition_to("SOME_UNMAPPED_STATE")

        anim_mgr.play.assert_called_with("idle")

    def test_sleep_state_maps_to_sleep_animation(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        CharacterStateManager(sm, anim_mgr)

        sm.transition_to("SLEEP")

        anim_mgr.play.assert_called_with("sleep")

    def test_gaming_state_maps_to_game_animation(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        CharacterStateManager(sm, anim_mgr)

        sm.transition_to("GAMING")

        anim_mgr.play.assert_called_with("game")

    def test_state_change_emits_character_state_changed(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        CharacterStateManager(sm, anim_mgr)

        received = []
        sm.event_bus.subscribe("CHARACTER_STATE_CHANGED", lambda **kwargs: received.append(kwargs))

        sm.transition_to("THINKING", reason="teste")

        # EventBus is a process-wide singleton, so earlier tests' CharacterStateManager
        # instances in this same file may still be subscribed to STATE_CHANGED too (and
        # re-fire here) — assert the expected event is present, not that it's the only one.
        assert {"state": "THINKING", "animation": "thinking", "reason": "teste"} in received


class TestEmotionIndependentOfFunctionalState:
    """FASE 13 — functional state (what Silva is doing) and emotion (how she
    feels) used to share one field/state machine, so a GAMING functional
    state and a HAPPY emotional reaction from the AI would clobber each
    other. This is the core behavior the split is for."""

    def test_emotion_is_shown_while_idle(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)

        char_mgr.set_emotion("HAPPY")

        anim_mgr.play.assert_called_with("happy")

    def test_emotion_is_shown_while_talking(self):
        sm = StateMachine("TALKING")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)

        char_mgr.set_emotion("SAD")

        anim_mgr.play.assert_called_with("sad")

    def test_busy_functional_state_takes_priority_over_emotion(self):
        """GAMING must keep its own sprite even if an emotion is set — no art
        combines the two, and the functional state is what's actually true."""
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)
        char_mgr.set_emotion("HAPPY")
        anim_mgr.reset_mock()

        sm.transition_to("GAMING")

        anim_mgr.play.assert_called_with("game")

    def test_emotion_reappears_automatically_after_returning_to_idle(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)
        char_mgr.set_emotion("EXCITED")

        sm.transition_to("GAMING")
        anim_mgr.reset_mock()
        sm.transition_to("IDLE")

        anim_mgr.play.assert_called_with("excited")

    def test_setting_emotion_while_busy_does_not_change_the_visible_sprite(self):
        sm = StateMachine("GAMING")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)
        anim_mgr.reset_mock()

        char_mgr.set_emotion("ANGRY")

        anim_mgr.play.assert_called_with("game")

    def test_unrecognized_emotion_is_ignored_not_crashed(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)

        char_mgr.set_emotion("NOT_A_REAL_EMOTION")

        anim_mgr.play.assert_called_with("idle")

    def test_none_emotion_clears_it_back_to_plain_functional_sprite(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)
        char_mgr.set_emotion("HAPPY")

        char_mgr.set_emotion(None)

        anim_mgr.play.assert_called_with("idle")

    def test_set_emotion_emits_emotion_changed(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)
        received = []
        sm.event_bus.subscribe("EMOTION_CHANGED", lambda **kwargs: received.append(kwargs))

        char_mgr.set_emotion("BRAVE", reason="teste")

        assert {"emotion": "BRAVE", "reason": "teste"} in received

    def test_activity_emotions_like_read_and_drink_are_valid(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)

        char_mgr.set_emotion("READ")

        anim_mgr.play.assert_called_with("read")
