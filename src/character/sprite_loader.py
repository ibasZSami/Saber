import os
import logging
from typing import Optional, Tuple

import numpy as np
from PIL import Image
from PySide6.QtGui import QPixmap, QImage

# Minimum consecutive fully-transparent rows that counts as a real gap between
# two disconnected shapes (as opposed to just a thin part of the body, like a neck).
MIN_GAP_ROWS = 2
# Height fraction below which caption/gap detection doesn't look — real character
# content is expected up here, so a false "gap" this early would be noise.
GAP_SEARCH_START = 0.30
GAP_SEARCH_END = 0.98
# Used only when no real transparent gap is found: assume anything below this
# fraction of the image height risks being a caption baked into the sheet.
NO_GAP_FALLBACK_HEIGHT = 0.75
# A column run narrower than this fraction of the image width is treated as
# stray noise (e.g. antialiasing bleed) rather than a real character pose.
MIN_FRAME_WIDTH_RATIO = 0.08


class SpriteLoader:
    """Loads a single representative pose per character action from this asset
    pack's sprite sheets.

    The sheets are inconsistent: some are clean multi-pose strips, others have a
    Portuguese caption + folder icon baked into the bottom of the image. Trusting a
    fixed frame count per action (the original approach) sliced through poses
    incorrectly and let captions leak into the displayed image. Instead, this reads
    the alpha channel directly to find one clean, undamaged pose:
    1. Find where the character's silhouette ends vertically, using a real gap of
       transparent rows (or a conservative height fraction if there's no gap).
    2. Within that region, pick the widest contiguous run of opaque columns — the
       most likely candidate for a full, uncropped pose.
    """

    def __init__(self, assets_dir: str):
        self.assets_dir = assets_dir
        self.cache = {}

    def pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        if pil_image.mode != "RGBA":
            pil_image = pil_image.convert("RGBA")
        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimage)

    def _find_content_bottom(self, alpha: np.ndarray) -> int:
        h, _ = alpha.shape
        row_has_content = (alpha > 10).any(axis=1)
        lo, hi = int(h * GAP_SEARCH_START), int(h * GAP_SEARCH_END)
        run = 0
        for y in range(lo, hi):
            if not row_has_content[y]:
                run += 1
                if run >= MIN_GAP_ROWS:
                    return y - run + 1
            else:
                run = 0
        return max(1, int(h * NO_GAP_FALLBACK_HEIGHT))

    def _find_widest_frame(self, alpha_top: np.ndarray) -> Tuple[int, int]:
        _, w = alpha_top.shape
        col_has_content = (alpha_top > 10).any(axis=0)
        runs = []
        start = None
        for x in range(w):
            if col_has_content[x] and start is None:
                start = x
            elif not col_has_content[x] and start is not None:
                runs.append((start, x))
                start = None
        if start is not None:
            runs.append((start, w))

        runs = [r for r in runs if (r[1] - r[0]) > w * MIN_FRAME_WIDTH_RATIO]
        if not runs:
            return (0, w)
        return max(runs, key=lambda r: r[1] - r[0])

    def load_sprite(self, anim_name: str) -> Optional[QPixmap]:
        if anim_name in self.cache:
            return self.cache[anim_name]

        file_path = os.path.join(self.assets_dir, f"{anim_name}.png")
        if not os.path.exists(file_path):
            logging.warning(f"Asset file missing: {file_path}")
            return None

        try:
            img = Image.open(file_path).convert("RGBA")
            alpha = np.array(img)[:, :, 3]

            cut_y = self._find_content_bottom(alpha)
            x0, x1 = self._find_widest_frame(alpha[:cut_y, :])

            pixmap = self.pil_to_qpixmap(img.crop((x0, 0, x1, cut_y)))
            self.cache[anim_name] = pixmap
            return pixmap
        except Exception as e:
            logging.error(f"Error loading sprite {anim_name}: {e}")
            return None
