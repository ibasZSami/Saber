import os
import shutil
import logging
from PIL import Image

# Common install locations when Tesseract isn't on PATH (e.g. winget/default installer)
TESSERACT_FALLBACK_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

class OCRProvider:
    def extract_text(self, image: Image.Image) -> dict:
        raise NotImplementedError

class TesseractOCRProvider(OCRProvider):
    def __init__(self):
        try:
            import pytesseract
            self.pytesseract = pytesseract
            self.available = self._locate_binary()
        except ImportError:
            self.available = False
            logging.warning("pytesseract not installed. OCR will run in dummy mode.")

    def _locate_binary(self) -> bool:
        if shutil.which("tesseract"):
            return True
        for path in TESSERACT_FALLBACK_PATHS:
            if os.path.isfile(path):
                self.pytesseract.pytesseract.tesseract_cmd = path
                return True
        logging.warning(
            "Tesseract-OCR binary not found (checked PATH and default install paths). "
            "Install it from https://github.com/UB-Mannheim/tesseract to enable screen translation."
        )
        return False

    def extract_text(self, image: Image.Image) -> dict:
        if not self.available:
            return {
                "text": "",
                "language": "unknown",
                "confidence": 0.0,
                "error": "Tesseract-OCR não está instalado. Instale em https://github.com/UB-Mannheim/tesseract para usar a tradução de tela.",
            }

        try:
            text = self.pytesseract.image_to_string(image)
            return {
                "text": text.strip(),
                "language": "auto",
                "confidence": 0.85 if text.strip() else 0.0
            }
        except Exception as e:
            logging.error(f"Tesseract OCR Error: {e}")
            return {"text": "", "language": "unknown", "confidence": 0.0, "error": str(e)}
