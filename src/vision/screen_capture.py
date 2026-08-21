import mss
import mss.tools
from PIL import Image
import io
import base64


def encode_image_base64(img: Image.Image, max_width: int = 1120, quality: int = 85) -> str:
    """Downscales and JPEG-encodes an image for sending to a vision-capable AI model.

    1120px/quality 85 (up from 1024/70) — Llama-3.2 vision models tile input up to
    ~1120px on the long side, so the old 1024/70 defaults threw away resolution the
    model could actually use and added visible JPEG artifacting that made small text
    and UI details hard to read, a real cause of imprecise screen descriptions."""
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def capture_primary(self) -> Image.Image:
        monitor = self.sct.monitors[1] if len(self.sct.monitors) > 1 else self.sct.monitors[0]
        sct_img = self.sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        return img

    def capture_monitor(self, monitor_index: int = 1) -> Image.Image:
        idx = min(monitor_index, len(self.sct.monitors) - 1)
        monitor = self.sct.monitors[idx]
        sct_img = self.sct.grab(monitor)
        return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
