from unittest.mock import MagicMock

from PySide6.QtGui import QPixmap

from src.character.animation_manager import AnimationManager


class TestAnimationManagerStaticSprite:
    def test_play_switches_current_anim_and_emits_signal(self):
        loader = MagicMock()
        loader.load_sprite.side_effect = lambda name: QPixmap(10, 10)
        mgr = AnimationManager(loader)

        received = []
        mgr.frame_changed.connect(lambda pixmap: received.append(pixmap))

        mgr.play("sleep")

        assert mgr.current_anim == "sleep"
        assert len(received) == 1

    def test_play_falls_back_to_idle_when_sprite_missing(self):
        loader = MagicMock()
        loader.load_sprite.side_effect = lambda name: QPixmap(10, 10) if name == "idle" else None
        mgr = AnimationManager(loader)

        mgr.play("nonexistent_animation")

        assert mgr.current_anim == "idle"

    def test_get_current_frame_returns_none_when_no_sprite_loaded(self):
        loader = MagicMock()
        loader.load_sprite.return_value = None
        mgr = AnimationManager(loader)

        assert mgr.get_current_frame() is None

    def test_play_does_not_emit_when_sprite_unavailable(self):
        loader = MagicMock()
        loader.load_sprite.return_value = None
        mgr = AnimationManager(loader)

        received = []
        mgr.frame_changed.connect(lambda pixmap: received.append(pixmap))

        mgr.play("idle")

        assert received == []

    def test_already_loaded_sprite_is_reused_not_reloaded(self):
        loader = MagicMock()
        loader.load_sprite.side_effect = lambda name: QPixmap(10, 10)
        mgr = AnimationManager(loader)

        loader.load_sprite.reset_mock()
        mgr.play("idle")  # already loaded during load_all()

        loader.load_sprite.assert_not_called()
