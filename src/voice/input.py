import logging
import threading
import time
from PySide6.QtCore import QObject, Signal

SAMPLE_RATE = 16000
MIN_AUDIO_SECONDS = 0.3

# faster-whisper/CTranslate2 model objects aren't documented as safe for
# concurrent inference from multiple threads. VoiceInput and SystemAudioListener
# can share one WhisperModel instance (system_audio.py's model_provider), and
# both transcribe on their own background threads (e.g. the user talks while
# game audio is also being captured) — this serializes every transcribe() call
# across both, regardless of which model instance is in play.
TRANSCRIBE_LOCK = threading.Lock()

# Simple energy-based voice activity detection for hands-free mode.
SILENCE_RMS_THRESHOLD = 500      # int16 RMS energy below this = silence
SILENCE_DURATION_S = 0.8         # how long silence must last before an utterance is considered done
MAX_UTTERANCE_SECONDS = 15       # safety cap so one long noise doesn't record forever


class VoiceInput(QObject):
    speech_recognized = Signal(str)
    transcription_failed = Signal(str)  # human-readable reason, so the UI/state can recover
    listening_started = Signal()
    listening_stopped = Signal()
    hands_free_toggled = Signal(bool)

    def __init__(self, language: str = "pt", model_size: str = "small"):
        super().__init__()
        self.language = language
        self.model_size = model_size
        self.is_listening = False
        self._frames = []
        self._lock = threading.Lock()
        self._stream = None
        self._model = None
        self._model_load_failed = False
        self._model_lock = threading.Lock()

        self.hands_free_enabled = False
        self._hands_free_thread = None
        self._hands_free_stop_event = threading.Event()

    def warm_up_model_async(self):
        """Loads (and downloads, if needed) the whisper model in the background so the
        first real Push-to-Talk use isn't stuck waiting on it."""
        threading.Thread(target=self._ensure_model, daemon=True).start()

    def _ensure_model(self):
        with self._model_lock:
            if self._model is not None or self._model_load_failed:
                return self._model
            try:
                from faster_whisper import WhisperModel
                logging.info(f"Loading faster-whisper model ({self.model_size})...")
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                logging.info("faster-whisper model ready.")
            except Exception as e:
                logging.error(f"Failed to load faster-whisper model: {e}")
                self._model_load_failed = True
            return self._model

    def start_listening(self):
        if self.is_listening or self.hands_free_enabled:
            return

        try:
            import sounddevice as sd
        except ImportError:
            logging.error("sounddevice não instalado; entrada de voz indisponível.")
            self.transcription_failed.emit("sounddevice não instalado.")
            return

        logging.info("VoiceInput listening started (Push-to-Talk F8 pressed)")
        self.is_listening = True
        with self._lock:
            self._frames = []
        self.listening_started.emit()

        def _callback(indata, frames, time_info, status):
            with self._lock:
                self._frames.append(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=_callback
            )
            self._stream.start()
        except Exception as e:
            logging.error(f"Failed to start microphone stream: {e}")
            self.is_listening = False
            self._stream = None
            self.transcription_failed.emit("Não consegui acessar o microfone.")

    def stop_listening(self):
        if not self.is_listening:
            return

        logging.info("VoiceInput listening stopped")
        self.is_listening = False
        self.listening_stopped.emit()

        if self._stream is None:
            return

        try:
            self._stream.stop()
            self._stream.close()
        except Exception as e:
            logging.error(f"Error closing microphone stream: {e}")
        finally:
            self._stream = None

        with self._lock:
            frames, self._frames = self._frames, []

        threading.Thread(target=self._transcribe, args=(frames,), daemon=True).start()

    def set_hands_free(self, enabled: bool):
        if enabled == self.hands_free_enabled:
            return
        self.hands_free_enabled = enabled
        self.hands_free_toggled.emit(enabled)
        if enabled:
            self._start_hands_free()
        else:
            self._stop_hands_free()

    def _start_hands_free(self):
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            logging.error(f"Dependência ausente para modo mãos-livres: {e}")
            self.hands_free_enabled = False
            self.hands_free_toggled.emit(False)
            self.transcription_failed.emit("Modo mãos-livres indisponível (dependência ausente).")
            return

        self._hands_free_stop_event.clear()
        logging.info("Hands-free voice mode enabled")

        def _run():
            buffer = []
            speaking = False
            silence_start = None
            speech_start = None

            def callback(indata, frames, time_info, status):
                nonlocal buffer, speaking, silence_start, speech_start
                if self._hands_free_stop_event.is_set():
                    return

                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                now = time.monotonic()

                if rms > SILENCE_RMS_THRESHOLD:
                    if not speaking:
                        speaking = True
                        speech_start = now
                        buffer = []
                        self.listening_started.emit()
                    silence_start = None
                    buffer.append(indata.copy())
                elif speaking:
                    buffer.append(indata.copy())
                    if silence_start is None:
                        silence_start = now

                    finished_by_silence = (now - silence_start) >= SILENCE_DURATION_S
                    finished_by_timeout = (now - speech_start) >= MAX_UTTERANCE_SECONDS
                    if finished_by_silence or finished_by_timeout:
                        speaking = False
                        self.listening_stopped.emit()
                        utterance, buffer = buffer, []
                        threading.Thread(target=self._transcribe, args=(utterance,), daemon=True).start()

            try:
                with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
                    while not self._hands_free_stop_event.wait(timeout=0.1):
                        pass
            except Exception as e:
                logging.error(f"Hands-free microphone error: {e}")
                self.transcription_failed.emit("Erro no microfone durante o modo mãos-livres.")
            finally:
                logging.info("Hands-free voice mode disabled")

        self._hands_free_thread = threading.Thread(target=_run, daemon=True)
        self._hands_free_thread.start()

    def _stop_hands_free(self):
        self._hands_free_stop_event.set()

    def _transcribe(self, frames):
        if not frames:
            self.transcription_failed.emit("Nenhum áudio capturado.")
            return

        try:
            import numpy as np
            audio = np.concatenate(frames, axis=0).flatten().astype(np.float32) / 32768.0
        except Exception as e:
            logging.error(f"Failed to prepare captured audio: {e}")
            self.transcription_failed.emit("Erro ao processar o áudio.")
            return

        if audio.size < SAMPLE_RATE * MIN_AUDIO_SECONDS:
            logging.info("Audio too short (segure o F8 enquanto fala), skipping transcription.")
            self.transcription_failed.emit("Fala muito curta — segure o F8 enquanto fala e solte no final.")
            return

        model = self._ensure_model()
        if not model:
            self.transcription_failed.emit("Não consegui carregar o modelo de reconhecimento de voz.")
            return

        try:
            # segments is a lazy generator — faster-whisper does the actual decoding
            # while it's iterated, not during the transcribe() call itself, so the
            # lock has to cover list(segments) too or two threads sharing this model
            # could still decode concurrently.
            with TRANSCRIBE_LOCK:
                segments, _ = model.transcribe(
                    audio,
                    language=self.language,
                    beam_size=5,
                    best_of=5,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=300),
                )
                segments = list(segments)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                self.speech_recognized.emit(text)
            else:
                self.transcription_failed.emit("Não entendi o que você disse.")
        except Exception as e:
            logging.error(f"faster-whisper transcription error: {e}")
            self.transcription_failed.emit("Erro ao transcrever o áudio.")
