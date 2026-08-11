from unittest.mock import MagicMock

from src.vision.translation import ScreenTranslationManager


class TestScreenTranslationManager:
    def test_returns_extracted_text_on_success(self):
        ocr = MagicMock()
        ocr.extract_text.return_value = {"text": "hello world"}
        mgr = ScreenTranslationManager(MagicMock(), ocr_provider=ocr)

        result = mgr.translate_current_screen()

        assert result["success"] is True
        assert result["original_text"] == "hello world"

    def test_reports_ocr_error_message_when_text_empty(self):
        ocr = MagicMock()
        ocr.extract_text.return_value = {"text": "", "error": "Tesseract-OCR não está instalado."}
        mgr = ScreenTranslationManager(MagicMock(), ocr_provider=ocr)

        result = mgr.translate_current_screen()

        assert result["success"] is False
        assert "Tesseract-OCR" in result["translated_text"]

    def test_generic_message_when_no_error_provided(self):
        ocr = MagicMock()
        ocr.extract_text.return_value = {"text": ""}
        mgr = ScreenTranslationManager(MagicMock(), ocr_provider=ocr)

        result = mgr.translate_current_screen()

        assert result["success"] is False
        assert result["translated_text"]
