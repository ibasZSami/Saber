from unittest.mock import patch, MagicMock

from src.vision.ocr import TesseractOCRProvider, TESSERACT_FALLBACK_PATHS


class TestLocateBinary:
    @patch("src.vision.ocr.shutil.which", return_value="C:\\tesseract.exe")
    def test_found_on_path(self, mock_which):
        provider = TesseractOCRProvider()
        assert provider.available is True

    @patch("src.vision.ocr.os.path.isfile")
    @patch("src.vision.ocr.shutil.which", return_value=None)
    def test_found_in_fallback_path(self, mock_which, mock_isfile):
        mock_isfile.side_effect = lambda p: p == TESSERACT_FALLBACK_PATHS[0]
        provider = TesseractOCRProvider()
        assert provider.available is True
        assert provider.pytesseract.pytesseract.tesseract_cmd == TESSERACT_FALLBACK_PATHS[0]

    @patch("src.vision.ocr.os.path.isfile", return_value=False)
    @patch("src.vision.ocr.shutil.which", return_value=None)
    def test_not_found_anywhere(self, mock_which, mock_isfile):
        provider = TesseractOCRProvider()
        assert provider.available is False


class TestExtractText:
    @patch("src.vision.ocr.os.path.isfile", return_value=False)
    @patch("src.vision.ocr.shutil.which", return_value=None)
    def test_unavailable_returns_actionable_error(self, mock_which, mock_isfile):
        provider = TesseractOCRProvider()
        result = provider.extract_text(image=None)
        assert result["text"] == ""
        assert "Tesseract-OCR" in result["error"]

    @patch("src.vision.ocr.shutil.which", return_value="tesseract")
    def test_success_strips_and_reports_confidence(self, mock_which):
        provider = TesseractOCRProvider()
        provider.pytesseract = MagicMock()
        provider.pytesseract.image_to_string.return_value = "  texto extraido  "

        result = provider.extract_text(image=MagicMock())

        assert result["text"] == "texto extraido"
        assert result["confidence"] > 0

    @patch("src.vision.ocr.shutil.which", return_value="tesseract")
    def test_empty_result_has_zero_confidence(self, mock_which):
        provider = TesseractOCRProvider()
        provider.pytesseract = MagicMock()
        provider.pytesseract.image_to_string.return_value = "   "

        result = provider.extract_text(image=MagicMock())

        assert result["text"] == ""
        assert result["confidence"] == 0.0

    @patch("src.vision.ocr.shutil.which", return_value="tesseract")
    def test_exception_during_ocr_is_handled(self, mock_which):
        provider = TesseractOCRProvider()
        provider.pytesseract = MagicMock()
        provider.pytesseract.image_to_string.side_effect = RuntimeError("boom")

        result = provider.extract_text(image=MagicMock())

        assert result["text"] == ""
        assert "boom" in result["error"]
