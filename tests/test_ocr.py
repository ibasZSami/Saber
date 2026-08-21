from unittest.mock import patch, MagicMock

from src.vision.ocr import TesseractOCRProvider, TESSERACT_FALLBACK_PATHS, _group_words_into_lines


def _sample_image_to_data():
    """Two lines: 'You ok?' (block 1, line 1, two words) and 'Yes' (block 1,
    line 2, one word), plus a noise row (empty text, conf=-1) the way
    pytesseract commonly returns for block/paragraph-level rows."""
    return {
        "text": ["", "You", "ok?", "Yes"],
        "conf": [-1, 96.5, 91.0, 88.0],
        "left": [0, 10, 45, 10],
        "top": [0, 20, 20, 50],
        "width": [0, 30, 25, 20],
        "height": [0, 15, 15, 15],
        "block_num": [1, 1, 1, 1],
        "par_num": [1, 1, 1, 1],
        "line_num": [1, 1, 1, 2],
    }


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


class TestGroupWordsIntoLines:
    def test_groups_words_on_the_same_line_together(self):
        blocks = _group_words_into_lines(_sample_image_to_data(), min_confidence=30.0)
        by_text = {b.text: b for b in blocks}
        assert "You ok?" in by_text

    def test_separate_lines_stay_separate(self):
        blocks = _group_words_into_lines(_sample_image_to_data(), min_confidence=30.0)
        texts = {b.text for b in blocks}
        assert texts == {"You ok?", "Yes"}

    def test_line_box_is_the_union_of_its_words(self):
        blocks = _group_words_into_lines(_sample_image_to_data(), min_confidence=30.0)
        line = next(b for b in blocks if b.text == "You ok?")
        assert line.x == 10  # min left
        assert line.y == 20
        assert line.width == 60  # from x=10 to right=70 (45+25)
        assert line.height == 15

    def test_empty_text_rows_are_skipped(self):
        blocks = _group_words_into_lines(_sample_image_to_data(), min_confidence=30.0)
        assert all(b.text.strip() for b in blocks)

    def test_low_confidence_words_are_filtered_out(self):
        data = _sample_image_to_data()
        data["conf"][1] = 5.0  # "You" now below threshold
        blocks = _group_words_into_lines(data, min_confidence=30.0)
        by_text = {b.text: b for b in blocks}
        assert "ok?" in by_text
        assert "You ok?" not in by_text

    def test_confidence_is_averaged_across_words_in_a_line(self):
        blocks = _group_words_into_lines(_sample_image_to_data(), min_confidence=30.0)
        line = next(b for b in blocks if b.text == "You ok?")
        assert line.confidence == (96.5 + 91.0) / 2

    def test_empty_input_returns_no_blocks(self):
        empty = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": [],
                  "block_num": [], "par_num": [], "line_num": []}
        assert _group_words_into_lines(empty, min_confidence=30.0) == []


class TestExtractStructured:
    @patch("src.vision.ocr.os.path.isfile", return_value=False)
    @patch("src.vision.ocr.shutil.which", return_value=None)
    def test_unavailable_returns_empty_list(self, mock_which, mock_isfile):
        provider = TesseractOCRProvider()
        assert provider.extract_structured(image=None) == []

    @patch("src.vision.ocr.shutil.which", return_value="tesseract")
    def test_success_returns_text_blocks_with_positions(self, mock_which):
        provider = TesseractOCRProvider()
        provider.pytesseract = MagicMock()
        provider.pytesseract.image_to_data.return_value = _sample_image_to_data()

        blocks = provider.extract_structured(image=MagicMock())

        texts = {b.text for b in blocks}
        assert texts == {"You ok?", "Yes"}

    @patch("src.vision.ocr.shutil.which", return_value="tesseract")
    def test_exception_during_structured_ocr_is_handled(self, mock_which):
        provider = TesseractOCRProvider()
        provider.pytesseract = MagicMock()
        provider.pytesseract.image_to_data.side_effect = RuntimeError("boom")

        assert provider.extract_structured(image=MagicMock()) == []
