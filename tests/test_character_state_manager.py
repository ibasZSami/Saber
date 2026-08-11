from unittest.mock import MagicMock

from src.character.state_manager import CharacterStateManager
from src.core.state_machine import StateMachine


class TestCharacterStateManager:
    def test_set_state_uppercases_and_delegates(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        char_mgr = CharacterStateManager(sm, anim_mgr)

        char_mgr.set_state("happy", reason="teste")

        assert sm.get_state() == "HAPPY"

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
