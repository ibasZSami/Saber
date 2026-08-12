import os
import logging
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image
from PySide6.QtGui import QPixmap, QImage

# A pixel counts as part of the character if its alpha is above this.
ALPHA_THRESHOLD = 10


class SpriteLoader:
    """Loads a single representative pose per character action from a sprite pack.

    Different asset packs bake in different kinds of junk around the actual pose:
    a caption + icon at the bottom, a sliver of a neighboring sprite bleeding in
    at an edge, several near-duplicate poses side by side. Trusting a fixed frame
    count/crop per action broke on every pack tried so far. Instead, this reads
    the alpha channel directly and keeps only the *largest connected blob* of
    opaque pixels — the character is reliably the biggest contiguous shape in
    the image; captions, icons, and bleed fragments are reliably smaller and
    disconnected from it.
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

    def _largest_component_bbox(self, mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Returns the (x0, y0, x1, y1) bounding box of the largest connected
        group of True pixels in `mask`, or None if `mask` is empty. Uses OpenCV's
        vectorized connected-components (already a project dependency) instead of
        a pure-Python flood fill — ~20x faster, which matters since this runs
        synchronously at startup for every sprite."""
        num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8), connectivity=4
        )
        if num_labels <= 1:
            return None

        # Label 0 is the background; pick the largest remaining component by area.
        areas = stats[1:, cv2.CC_STAT_AREA]
        best_label = 1 + int(np.argmax(areas))
        x, y, w, h = stats[best_label, cv2.CC_STAT_LEFT], stats[best_label, cv2.CC_STAT_TOP], \
            stats[best_label, cv2.CC_STAT_WIDTH], stats[best_label, cv2.CC_STAT_HEIGHT]
        return (int(x), int(y), int(x + w), int(y + h))

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

            bbox = self._largest_component_bbox(alpha > ALPHA_THRESHOLD)
            cropped = img.crop(bbox) if bbox else img

            pixmap = self.pil_to_qpixmap(cropped)
            self.cache[anim_name] = pixmap
            return pixmap
        except Exception as e:
            logging.error(f"Error loading sprite {anim_name}: {e}")
            return None
