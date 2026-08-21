import logging
from src.vision.screen_capture import ScreenCapture
from src.vision.ocr import OCRProvider, TesseractOCRProvider

class ScreenTranslationManager:
    def __init__(self, capture: ScreenCapture, ocr_provider: OCRProvider = None):
        self.capture = capture
        self.ocr = ocr_provider or TesseractOCRProvider()

    def translate_current_screen(self, target_lang: str = "pt") -> dict:
        logging.info("Explicit screen translation requested.")
        img = self.capture.capture_primary()
        ocr_res = self.ocr.extract_text(img)

        extracted_text = ocr_res.get("text", "")
        if not extracted_text:
            message = ocr_res.get("error") or "Não consegui ler nenhum texto legível na tela no momento."
            return {
                "original_text": "",
                "translated_text": message,
                "success": False
            }

        return {
            "original_text": extracted_text,
            "translated_text": extracted_text, # Will be translated by AI Provider
            "success": True
        }
