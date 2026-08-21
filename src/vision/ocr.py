import os
import shutil
import logging
from dataclasses import dataclass
from typing import List

from PIL import Image

# Common install locations when Tesseract isn't on PATH (e.g. winget/default installer)
TESSERACT_FALLBACK_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

# Tesseract reports word-level confidence 0-100 (or -1 for non-text regions
# like inter-line whitespace) — below this, a "word" is noise more often
# than a real character, not worth showing/translating.
DEFAULT_MIN_CONFIDENCE = 30.0


@dataclass(frozen=True)
class TextBlock:
    """One line of detected on-screen text with its position — FASE 4. Built
    by grouping Tesseract's word-level boxes back into lines (see
    _group_words_into_lines) rather than exposing per-word boxes: a
    translation overlay covering each word separately would look
    fragmented, and "line" is the natural unit a reader's eye follows."""

    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


class OCRProvider:
    def extract_text(self, image: Image.Image) -> dict:
        raise NotImplementedError

    def extract_structured(self, image: Image.Image, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> List[TextBlock]:
        raise NotImplementedError


def _group_words_into_lines(data: dict, min_confidence: float) -> List[TextBlock]:
    """Groups pytesseract's image_to_data() word-level output back into
    lines, keyed by (block_num, par_num, line_num) — words tesseract itself
    already considers part of the same line. A line's box is the union of
    its words' boxes; its confidence is the mean of its words' confidences."""
    lines: dict = {}
    n = len(data.get("text", []))
    for i in range(n):
        text = (data["text"][i] or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not text or conf < min_confidence:
            continue

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        left, top = data["left"][i], data["top"][i]
        right, bottom = left + data["width"][i], top + data["height"][i]

        if key not in lines:
            lines[key] = {"words": [text], "left": left, "top": top, "right": right, "bottom": bottom, "confs": [conf]}
        else:
            line = lines[key]
            line["words"].append(text)
            line["left"] = min(line["left"], left)
            line["top"] = min(line["top"], top)
            line["right"] = max(line["right"], right)
            line["bottom"] = max(line["bottom"], bottom)
            line["confs"].append(conf)

    blocks = []
    for line in lines.values():
        blocks.append(TextBlock(
            text=" ".join(line["words"]),
            x=line["left"], y=line["top"],
            width=line["right"] - line["left"], height=line["bottom"] - line["top"],
            confidence=sum(line["confs"]) / len(line["confs"]),
        ))
    return blocks


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

    def extract_structured(self, image: Image.Image, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> List[TextBlock]:
        """Bounding-box-per-line OCR — FASE 4, used by the translation
        overlay (src/vision/translation_engine.py, FASE 5) to know WHERE to
        draw each translated line, not just what the screen says."""
        if not self.available:
            return []
        try:
            data = self.pytesseract.image_to_data(image, output_type=self.pytesseract.Output.DICT)
            return _group_words_into_lines(data, min_confidence)
        except Exception as e:
            logging.error(f"Tesseract structured OCR error: {e}")
            return []
