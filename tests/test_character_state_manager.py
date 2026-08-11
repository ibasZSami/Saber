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

        anim_mgr.play.assert_called_with("talking", loop=True)

    def test_unknown_state_falls_back_to_idle_animation(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        CharacterStateManager(sm, anim_mgr)

        sm.transition_to("SOME_UNMAPPED_STATE")

        anim_mgr.play.assert_called_with("idle", loop=False)

    def test_non_looping_state_passes_loop_false(self):
        sm = StateMachine("IDLE")
        anim_mgr = MagicMock()
        CharacterStateManager(sm, anim_mgr)

        sm.transition_to("HAPPY")

        anim_mgr.play.assert_called_with("happy", loop=False)
