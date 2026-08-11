import logging
from typing import Dict, Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap
from src.character.sprite_loader import SpriteLoader

class AnimationManager(QObject):
    """Shows a single static, representative pose per character state instead of
    cycling through sprite frames — the source sheets are inconsistent (variable
    pose counts, some with captions baked in), so animating them looked broken
    rather than fluid. See SpriteLoader for how each pose is extracted."""

    frame_changed = Signal(QPixmap)

    def __init__(self, sprite_loader: SpriteLoader):
        super().__init__()
        self.sprite_loader = sprite_loader
        self.current_anim: str = "idle"

        self.sprites: Dict[str, QPixmap] = {}
        self.load_all()
        self.play("idle")

    def load_all(self):
        common_anims = [
            "idle", "walk", "run", "talking", "thinking", "happy", "sad",
            "angry", "surprised", "shy", "serious", "confused", "brave", "funny",
            "sleep", "eat", "drink", "read", "work_pc", "game", "interaction",
            "defend", "attack_basic", "attack_combo", "attack_heavy", "attack_final",
            "skill", "hurt", "death", "teleport_in", "teleport_out", "crouch", "fall", "get_up"
        ]
        for anim in common_anims:
            pixmap = self.sprite_loader.load_sprite(anim)
            if pixmap:
                self.sprites[anim] = pixmap

    def play(self, anim_name: str):
        if anim_name not in self.sprites:
            pixmap = self.sprite_loader.load_sprite(anim_name)
            if pixmap:
                self.sprites[anim_name] = pixmap
            else:
                logging.warning(f"Animation {anim_name} not available, falling back to idle.")
                anim_name = "idle"

        self.current_anim = anim_name
        frame = self.get_current_frame()
        if frame is not None:
            self.frame_changed.emit(frame)

    def get_current_frame(self) -> Optional[QPixmap]:
        return self.sprites.get(self.current_anim)
