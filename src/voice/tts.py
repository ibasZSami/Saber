import logging
import asyncio
import tempfile
import os

DEFAULT_VOICE = "pt-BR-AntonioNeural"


def _to_percent_string(multiplier: float) -> str:
    """Converts a 1.0-is-normal float multiplier (e.g. speed=1.1) into the
    '+N%'/'-N%' string edge_tts's SSML prosody params expect."""
    pct = round((multiplier - 1.0) * 100)
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct}%"


class TTSProvider:
    def speak(self, text: str, voice: str = DEFAULT_VOICE, volume: float = 1.0, speed: float = 1.0, pitch: str = "+0Hz") -> bool:
        raise NotImplementedError

class EdgeTTSProvider(TTSProvider):
    def speak(self, text: str, voice: str = DEFAULT_VOICE, volume: float = 1.0, speed: float = 1.0, pitch: str = "+0Hz") -> bool:
        try:
            import edge_tts
            import pygame

            rate_str = _to_percent_string(speed)
            volume_str = _to_percent_string(volume)

            async def _generate():
                communicate = edge_tts.Communicate(text, voice, rate=rate_str, volume=volume_str, pitch=pitch)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    temp_path = fp.name
                await communicate.save(temp_path)
                return temp_path

            # Run async edge_tts
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            mp3_path = loop.run_until_complete(_generate())
            loop.close()

            # Play audio using winsound or pygame if available
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(mp3_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
            except Exception:
                pass
            finally:
                if os.path.exists(mp3_path):
                    try:
                        os.remove(mp3_path)
                    except Exception:
                        pass
            return True
        except Exception as e:
            logging.error(f"EdgeTTS Error: {e}")
            return False

class Pyttsx3Provider(TTSProvider):
    def __init__(self):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self._select_male_voice()
        except Exception as e:
            self.engine = None
            logging.warning(f"pyttsx3 init failed: {e}")

    def _select_male_voice(self):
        """Best-effort: pyttsx3's API doesn't expose reliable gender metadata
        across backends, so this falls back to common name/id hints.

        Careful: "male" is a substring of "female", so any female-flagged
        voice must be excluded explicitly rather than just checking "male in ...".
        """
        try:
            for v in self.engine.getProperty("voices"):
                name = (v.name or "").lower()
                vid = (v.id or "").lower()
                gender = (getattr(v, "gender", "") or "").lower()

                is_female = "female" in gender or "female" in name or "female" in vid
                is_male_hint = "male" in gender or any(
                    hint in name or hint in vid for hint in ("daniel", "antonio", "male")
                )

                if is_male_hint and not is_female:
                    self.engine.setProperty("voice", v.id)
                    return
        except Exception as e:
            logging.debug(f"Could not select a male pyttsx3 voice: {e}")

    def speak(self, text: str, voice: str = "", volume: float = 1.0, speed: float = 1.0, pitch: str = "+0Hz") -> bool:
        if not self.engine:
            return False
        try:
            self.engine.setProperty("volume", max(0.0, min(1.0, volume)))
            self.engine.setProperty("rate", int(200 * speed))  # pyttsx3 rate is words/minute, ~200 default
            self.engine.say(text)
            self.engine.runAndWait()
            return True
        except Exception as e:
            logging.error(f"pyttsx3 speak error: {e}")
            return False


class FallbackTTSProvider(TTSProvider):
    """Auto-recovery for the most common real failure mode of the default
    voice setup: EdgeTTS needs network access (it streams synthesis from
    Microsoft's service), so a dropped connection silently loses ALL voice
    output today — speak() already swallows the exception (see above), so
    nothing tells the user anything went wrong; Silva just goes quiet.

    Wraps a primary provider with a fallback that's tried only when the
    primary's speak() reports failure (returns False) — normally pyttsx3,
    which is fully offline. Keeps FASE 18's Diagnóstico/Atividade additions
    honest: an EdgeTTS outage becomes "spoke via fallback" instead of a
    silent no-op nothing else in the app can see."""

    def __init__(self, primary: TTSProvider, fallback: TTSProvider):
        self.primary = primary
        self.fallback = fallback

    def speak(self, text: str, voice: str = DEFAULT_VOICE, volume: float = 1.0, speed: float = 1.0, pitch: str = "+0Hz") -> bool:
        if self.primary.speak(text, voice=voice, volume=volume, speed=speed, pitch=pitch):
            return True
        logging.warning("Primary TTS failed — falling back to local voice.")
        return self.fallback.speak(text, voice=voice, volume=volume, speed=speed, pitch=pitch)
