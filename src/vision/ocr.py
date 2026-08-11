import logging
from PIL import Image

class OCRProvider:
    def extract_text(self, image: Image.Image) -> dict:
        raise NotImplementedError

class TesseractOCRProvider(OCRProvider):
    def __init__(self):
        try:
            import pytesseract
            self.pytesseract = pytesseract
            self.available = True
        except ImportError:
            self.available = False
            logging.warning("pytesseract not installed. OCR will run in dummy mode.")

    def extract_text(self, image: Image.Image) -> dict:
        if not self.available:
            return {"text": "", "language": "unknown", "confidence": 0.0}

        try:
            text = self.pytesseract.image_to_string(image)
            return {
                "text": text.strip(),
                "language": "auto",
                "confidence": 0.85 if text.strip() else 0.0
            }
        except Exception as e:
            logging.error(f"Tesseract OCR Error: {e}")
            return {"text": "", "language": "unknown", "confidence": 0.0}
