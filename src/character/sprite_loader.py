import os
import re
import logging
from PIL import Image
from PySide6.QtGui import QPixmap, QImage

# Sprite dimensions map based on shimeji_animations_transparent README.txt
SPRITE_SPECS = {
    "base": {"width": 198, "height": 170, "frames": 1},
    "expressions": {"width": 222, "height": 110, "frames": 2},
    "idle": {"width": 230, "height": 89, "frames": 3},
    "walk": {"width": 276, "height": 89, "frames": 4},
    "run": {"width": 275, "height": 102, "frames": 4},
    "pull_sword": {"width": 237, "height": 118, "frames": 3},
    "fall": {"width": 214, "height": 125, "frames": 3},
    "crouch": {"width": 244, "height": 104, "frames": 3},
    "get_up": {"width": 231, "height": 113, "frames": 3},
    "attack_basic": {"width": 345, "height": 119, "frames": 3},
    "attack_combo": {"width": 254, "height": 150, "frames": 3},
    "attack_heavy": {"width": 472, "height": 128, "frames": 4},
    "attack_final": {"width": 360, "height": 134, "frames": 3},
    "skill": {"width": 428, "height": 135, "frames": 4},
    "defend": {"width": 241, "height": 115, "frames": 3},
    "hurt": {"width": 189, "height": 120, "frames": 3},
    "death": {"width": 232, "height": 101, "frames": 3},
    "teleport_in": {"width": 347, "height": 130, "frames": 4},
    "teleport_out": {"width": 185, "height": 130, "frames": 3},
    "sleep": {"width": 242, "height": 85, "frames": 3},
    "eat": {"width": 240, "height": 115, "frames": 3},
    "drink": {"width": 177, "height": 113, "frames": 3},
    "read": {"width": 266, "height": 116, "frames": 3},
    "work_pc": {"width": 285, "height": 125, "frames": 3},
    "game": {"width": 285, "height": 125, "frames": 3},
    "talking": {"width": 245, "height": 116, "frames": 3},
    "thinking": {"width": 221, "height": 125, "frames": 3},
    "happy": {"width": 182, "height": 110, "frames": 2},
    "sad": {"width": 270, "height": 115, "frames": 3},
    "angry": {"width": 276, "height": 94, "frames": 3},
    "surprised": {"width": 280, "height": 115, "frames": 3},
    "shy": {"width": 250, "height": 115, "frames": 3},
    "serious": {"width": 224, "height": 115, "frames": 3},
    "confused": {"width": 209, "height": 120, "frames": 3},
    "brave": {"width": 223, "height": 120, "frames": 3},
    "funny": {"width": 203, "height": 109, "frames": 3},
    "interaction": {"width": 445, "height": 135, "frames": 4},
    "avatar": {"width": 110, "height": 135, "frames": 1},
    "cursor": {"width": 250, "height": 125, "frames": 3},
    "sword": {"width": 212, "height": 129, "frames": 3},
    "sword_effects": {"width": 316, "height": 131, "frames": 3},
    "particles": {"width": 415, "height": 127, "frames": 4},
    "burst_aura": {"width": 360, "height": 141, "frames": 4},
    "ui_icons": {"width": 200, "height": 141, "frames": 4}
}

class SpriteLoader:
    def __init__(self, assets_dir: str):
        self.assets_dir = assets_dir
        self.cache = {}

    def pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        if pil_image.mode != "RGBA":
            pil_image = pil_image.convert("RGBA")
        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimage)

    def load_animation_frames(self, anim_name: str) -> list[QPixmap]:
        if anim_name in self.cache:
            return self.cache[anim_name]

        file_path = os.path.join(self.assets_dir, f"{anim_name}.png")
        if not os.path.exists(file_path):
            logging.warning(f"Asset file missing: {file_path}")
            return []

        try:
            img = Image.open(file_path)
            total_w, total_h = img.size

            spec = SPRITE_SPECS.get(anim_name)
            if spec:
                frame_count = spec["frames"]
            else:
                # Fallback estimation
                frame_count = max(1, round(total_w / total_h))

            frame_width = total_w // frame_count
            frames = []

            for i in range(frame_count):
                box = (i * frame_width, 0, (i + 1) * frame_width, total_h)
                frame_crop = img.crop(box)
                pixmap = self.pil_to_qpixmap(frame_crop)
                frames.append(pixmap)

            self.cache[anim_name] = frames
            return frames
        except Exception as e:
            logging.error(f"Error loading sprite strip {anim_name}: {e}")
            return []
