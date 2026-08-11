import base64
import io

from PIL import Image

from src.vision.screen_capture import encode_image_base64


class TestEncodeImageBase64:
    def test_returns_valid_base64_jpeg(self):
        img = Image.new("RGB", (50, 50), color="red")
        encoded = encode_image_base64(img)
        decoded_img = Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert decoded_img.format == "JPEG"

    def test_downscales_large_images(self):
        img = Image.new("RGB", (2000, 1000), color="blue")
        encoded = encode_image_base64(img, max_width=1024)
        decoded_img = Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert decoded_img.width == 1024
        assert decoded_img.height == 512

    def test_does_not_upscale_small_images(self):
        img = Image.new("RGB", (200, 100), color="green")
        encoded = encode_image_base64(img, max_width=1024)
        decoded_img = Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert decoded_img.width == 200

    def test_converts_rgba_to_rgb_for_jpeg(self):
        img = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
        encoded = encode_image_base64(img)
        decoded_img = Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert decoded_img.mode == "RGB"
