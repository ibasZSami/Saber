import logging
from typing import Dict, List, Optional
from PySide6.QtGui import QPixmap
from src.character.sprite_loader import SpriteLoader

class AnimationManager:
    def __init__(self, sprite_loader: SpriteLoader, default_fps: int = 12):
        self.sprite_loader = sprite_loader
        self.default_fps = default_fps

        self.current_anim: str = "idle"
        self.current_frame_idx: int = 0
        self.is_looping: bool = True
        self.is_playing: bool = True
        self.previous_anim: Optional[str] = None

        self.is_temporary: bool = False
        self.on_finished_callback = None

        # Preload animations dictionary
        self.animations: Dict[str, List[QPixmap]] = {}
        self.load_all()

    def load_all(self):
        common_anims = [
            "idle", "walk", "run", "talking", "thinking", "happy", "sad",
            "angry", "surprised", "shy", "serious", "confused", "brave", "funny",
            "sleep", "eat", "drink", "read", "work_pc", "game", "interaction",
            "defend", "attack_basic", "attack_combo", "attack_heavy", "attack_final",
            "skill", "hurt", "death", "teleport_in", "teleport_out", "crouch", "fall", "get_up"
        ]
        for anim in common_anims:
            frames = self.sprite_loader.load_animation_frames(anim)
            if frames:
                self.animations[anim] = frames

    def play(self, anim_name: str, loop: bool = True, temporary: bool = False, on_finished=None):
        if anim_name not in self.animations:
            frames = self.sprite_loader.load_animation_frames(anim_name)
            if frames:
                self.animations[anim_name] = frames
            else:
                logging.warning(f"Animation {anim_name} not available, falling back to idle.")
                anim_name = "idle"

        if temporary and self.current_anim != anim_name:
            self.previous_anim = self.current_anim
            self.is_temporary = True
        elif not temporary:
            self.is_temporary = False
            self.previous_anim = None

        self.current_anim = anim_name
        self.current_frame_idx = 0
        self.is_looping = loop
        self.is_playing = True
        self.on_finished_callback = on_finished

    def update(self) -> Optional[QPixmap]:
        if not self.is_playing or self.current_anim not in self.animations:
            return self.get_current_frame()

        frames = self.animations[self.current_anim]
        if not frames:
            return None

        pixmap = frames[self.current_frame_idx]
        self.current_frame_idx += 1

        if self.current_frame_idx >= len(frames):
            if self.is_looping:
                self.current_frame_idx = 0
            else:
                self.current_frame_idx = len(frames) - 1
                self.is_playing = False

                if self.on_finished_callback:
                    cb = self.on_finished_callback
                    self.on_finished_callback = None
                    cb()

                if self.is_temporary and self.previous_anim:
                    prev = self.previous_anim
                    self.is_temporary = False
                    self.previous_anim = None
                    self.play(prev, loop=True)

        return pixmap

    def get_current_frame(self) -> Optional[QPixmap]:
        frames = self.animations.get(self.current_anim)
        if frames and 0 <= self.current_frame_idx < len(frames):
            return frames[self.current_frame_idx]
        elif frames:
            return frames[0]
        return None
