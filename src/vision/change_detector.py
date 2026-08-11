import numpy as np
from PIL import Image
import logging

class ScreenChangeDetector:
    def __init__(self, threshold: float = 0.08):
        self.threshold = threshold
        self.last_img = None

    def has_changed(self, current_img: Image.Image) -> bool:
        if current_img is None:
            return False

        # Resize for fast comparison
        resized = current_img.resize((128, 128)).convert("L")
        arr = np.array(resized, dtype=np.float32)

        if self.last_img is None:
            self.last_img = arr
            return True

        diff = np.mean(np.abs(arr - self.last_img)) / 255.0
        self.last_img = arr

        changed = diff >= self.threshold
        if changed:
            logging.debug(f"Screen change detected (diff={diff:.4f})")
        return changed
