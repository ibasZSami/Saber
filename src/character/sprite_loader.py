import os
import logging
from typing import Optional, Tuple

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
        """Flood-fills each connected group of True pixels in `mask` and returns
        the (x0, y0, x1, y1) bounding box of the largest one, or None if `mask`
        is empty."""
        h, w = mask.shape
        visited = np.zeros_like(mask, dtype=bool)
        best_bbox = None
        best_size = 0

        ys, xs = np.where(mask)
        for start_y, start_x in zip(ys.tolist(), xs.tolist()):
            if visited[start_y, start_x]:
                continue

            stack = [(start_y, start_x)]
            visited[start_y, start_x] = True
            min_y = max_y = start_y
            min_x = max_x = start_x
            size = 0

            while stack:
                y, x = stack.pop()
                size += 1
                min_y, max_y = min(min_y, y), max(max_y, y)
                min_x, max_x = min(min_x, x), max(max_x, x)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))

            if size > best_size:
                best_size = size
                best_bbox = (min_x, min_y, max_x + 1, max_y + 1)

        return best_bbox

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
