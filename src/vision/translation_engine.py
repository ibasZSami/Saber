"""Translation Engine — FASE 5. Two things keep continuous on-screen
translation (FASE 7) fast enough to not feel laggy or flood the AI
provider:

1. A cache — identical text is never translated twice (src/vision/
   continuous_vision.py's OCR keeps re-detecting whatever's still on
   screen every tick; only genuinely NEW text should ever cost an AI call).
2. Batching — every new text block from one screen capture is translated
   in a SINGLE AI call (a numbered list in, a JSON map out), not one call
   per line.

Deliberately reuses the existing ai_provider.chat() (already used for
chat/spontaneous speech/research) instead of a dedicated translation API —
no new dependency, and chat() is prompt-content-agnostic: it just sends
whatever system prompt it's given, so a translation-specific instruction
here works the same way a conversational one does elsewhere."""

import json
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from src.core.event_bus import EventBus, TRANSLATION_BATCH_COMPLETED

TRANSLATION_SYSTEM_PROMPT = (
    "Você traduz textos de tela para português do Brasil. Vai receber uma lista numerada de "
    "textos curtos (rótulos de interface, falas de jogo, legendas). Responda SOMENTE com um "
    "objeto JSON puro — chave é o número (como string), valor é a tradução, nada mais, nada de "
    "texto fora do JSON. Preserve o tom curto/direto do original. Se um texto já estiver em "
    "português, ou não for traduzível (só números, símbolos, nome próprio), repita-o como está."
)


def _parse_translation_response(raw: str) -> dict:
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            return {}
        return json.loads(raw[start:end + 1])
    except Exception as e:
        logging.warning(f"Failed to parse translation response: {e}")
        return {}


class TranslationEngine:
    def __init__(self, ai_provider, event_bus: Optional[EventBus] = None):
        self.ai_provider = ai_provider
        self.event_bus = event_bus or EventBus()
        self._cache: Dict[str, str] = {}
        self._lock = threading.Lock()

    def cached(self, text: str) -> Optional[str]:
        with self._lock:
            return self._cache.get(text)

    def translate_batch(self, texts: List[str]) -> Dict[str, str]:
        """Synchronous — translates whatever in `texts` isn't already
        cached, in one AI call, and returns {original: translated} for
        every input (cached or freshly translated alike)."""
        start_time = time.time()
        result = {}
        to_translate = []
        with self._lock:
            for text in texts:
                cached = self._cache.get(text)
                if cached is not None:
                    result[text] = cached
                elif text not in to_translate:
                    to_translate.append(text)

        if to_translate:
            translated = self._translate_via_ai(to_translate)
            with self._lock:
                for original, translation in translated.items():
                    self._cache[original] = translation
                    result[original] = translation
            # Anything the AI response didn't cover (parse failure, missing
            # key for that index) falls back to the original text rather
            # than showing nothing over it.
            for text in to_translate:
                result.setdefault(text, text)

        self.event_bus.emit(
            TRANSLATION_BATCH_COMPLETED, total=len(texts), from_cache=len(texts) - len(to_translate),
            translated=len(to_translate), duration_seconds=time.time() - start_time,
        )
        return result

    def translate_batch_async(self, texts: List[str], on_done: Callable[[Dict[str, str]], None]):
        """Same as translate_batch but off the calling thread — the
        continuous translation loop (FASE 7) calls this so a slow AI call
        never blocks the next screen capture/OCR tick."""
        def _worker():
            try:
                on_done(self.translate_batch(texts))
            except Exception as e:
                logging.error(f"Translation batch failed: {e}")
                on_done({t: t for t in texts})
        threading.Thread(target=_worker, daemon=True).start()

    def _translate_via_ai(self, texts: List[str]) -> Dict[str, str]:
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
        try:
            raw = self.ai_provider.chat(numbered, TRANSLATION_SYSTEM_PROMPT, [], image_base64=None)
        except Exception as e:
            logging.error(f"Translation AI call failed: {e}")
            return {}
        parsed = _parse_translation_response(raw)
        result = {}
        for i, text in enumerate(texts):
            translation = parsed.get(str(i + 1))
            if isinstance(translation, str) and translation.strip():
                result[text] = translation.strip()
        return result

    def clear_cache(self):
        with self._lock:
            self._cache.clear()
