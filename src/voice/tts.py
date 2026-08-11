import logging
import asyncio
import tempfile
import os

class TTSProvider:
    def speak(self, text: str, voice: str = "pt-BR-FranciscaNeural", volume: float = 1.0, speed: float = 1.0):
        raise NotImplementedError

class EdgeTTSProvider(TTSProvider):
    def speak(self, text: str, voice: str = "pt-BR-FranciscaNeural", volume: float = 1.0, speed: float = 1.0):
        try:
            import edge_tts
            import pygame

            async def _generate():
                communicate = edge_tts.Communicate(text, voice)
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
        except Exception as e:
            logging.error(f"EdgeTTS Error: {e}")

class Pyttsx3Provider(TTSProvider):
    def __init__(self):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
        except Exception as e:
            self.engine = None
            logging.warning(f"pyttsx3 init failed: {e}")

    def speak(self, text: str, voice: str = "", volume: float = 1.0, speed: float = 1.0):
        if self.engine:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                logging.error(f"pyttsx3 speak error: {e}")
