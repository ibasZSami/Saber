import logging
import threading
import time

from PySide6.QtCore import QObject, Signal

from src.voice.input import (
    SAMPLE_RATE,
    MIN_AUDIO_SECONDS,
    SILENCE_DURATION_S,
    MAX_UTTERANCE_SECONDS,
    TRANSCRIBE_LOCK,
)
from src.voice.vad_segmenter import SpeechSegmenter

# soundcard hands back normalized float32 samples (roughly [-1, 1]), unlike the
# raw int16 PCM from the microphone path — this threshold is on that scale.
SYSTEM_AUDIO_RMS_THRESHOLD = 0.015
# Whisper hallucinates text on music/sound-effects fairly often; segments the
# model itself flags as likely-non-speech above this get discarded.
MAX_NO_SPEECH_PROB = 0.6
# Minimum gap between two AI-facing transcriptions, so continuous game/PC audio
# (which rarely goes fully silent) can't spam the conversation.
EMIT_COOLDOWN_S = 8.0
# How often to pull a chunk from the loopback recorder.
POLL_CHUNK_SECONDS = 0.1
# Windows' standard shared-mode mixer rate; captured audio is resampled from
# this down to 16kHz (what Whisper expects) before transcription.
CAPTURE_SAMPLE_RATE = 48000


class SystemAudioListener(QObject):
    """Listens to the computer's own audio output (game, video, any app sound)
    via WASAPI loopback (through the `soundcard` package) — not the microphone
    — so Silva can react to what's playing. Uses the same VAD-segment-then-
    transcribe approach as VoiceInput's hands-free mode, tuned for continuous,
    often-noisy system audio instead of a person pausing between sentences.
    """

    audio_transcribed = Signal(str)
    transcription_failed = Signal(str)
    listening_toggled = Signal(bool)

    def __init__(self, language: str = "pt", model_provider=None):
        super().__init__()
        self.language = language
        self._model_provider = model_provider
        self._own_model = None
        self._own_model_load_failed = False
        self._own_model_lock = threading.Lock()

        self.enabled = False
        self._stop_event = threading.Event()
        self._thread = None
        self._last_emit_time = 0.0

    def _ensure_model(self):
        if self._model_provider:
            return self._model_provider()
        with self._own_model_lock:
            if self._own_model is not None or self._own_model_load_failed:
                return self._own_model
            try:
                from faster_whisper import WhisperModel
                logging.info("Loading faster-whisper model for system audio (small)...")
                self._own_model = WhisperModel("small", device="cpu", compute_type="int8")
            except Exception as e:
                logging.error(f"Failed to load whisper model for system audio: {e}")
                self._own_model_load_failed = True
            return self._own_model

    def set_enabled(self, enabled: bool):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self._start()
        else:
            self._stop()

    def _get_loopback_mic(self, sc):
        speaker = sc.default_speaker()
        if speaker is None:
            return None
        return sc.get_microphone(id=str(speaker.name), include_loopback=True)

    def _start(self):
        try:
            import soundcard as sc
            import numpy as np
        except ImportError as e:
            logging.error(f"Dependência ausente para ouvir o áudio do sistema: {e}")
            self.enabled = False
            self.transcription_failed.emit("Ouvir o áudio do PC requer o pacote 'soundcard', que não foi encontrado.")
            self.listening_toggled.emit(False)
            return

        try:
            loopback_mic = self._get_loopback_mic(sc)
        except Exception as e:
            loopback_mic = None
            logging.error(f"Failed to resolve loopback device: {e}")

        if loopback_mic is None:
            logging.error("No loopback-capable output device found.")
            self.enabled = False
            self.transcription_failed.emit("Não encontrei um dispositivo de áudio para ouvir o som do sistema.")
            self.listening_toggled.emit(False)
            return

        self._stop_event.clear()
        logging.info(f"System audio listening enabled (device={loopback_mic.name!r})")
        chunk_frames = int(CAPTURE_SAMPLE_RATE * POLL_CHUNK_SECONDS)

        def _run():
            segmenter = SpeechSegmenter(SYSTEM_AUDIO_RMS_THRESHOLD, SILENCE_DURATION_S, MAX_UTTERANCE_SECONDS)

            try:
                with loopback_mic.recorder(samplerate=CAPTURE_SAMPLE_RATE) as recorder:
                    while not self._stop_event.is_set():
                        data = recorder.record(numframes=chunk_frames)
                        mono = data.mean(axis=1) if data.ndim > 1 else data
                        rms = float(np.sqrt(np.mean(mono.astype("float32") ** 2)))
                        now = time.monotonic()

                        chunk = segmenter.push(mono.copy(), rms, now)
                        if chunk is not None:
                            threading.Thread(
                                target=self._transcribe, args=(chunk,), daemon=True
                            ).start()
            except Exception as e:
                logging.error(f"System audio loopback error: {e}")
                self.transcription_failed.emit("Erro ao capturar o áudio do sistema.")
                # Without this, self.enabled stays True after the capture thread has
                # actually died (device disconnected, driver error, etc.) — set_enabled(True)
                # would then no-op on its "already enabled" check and never restart it.
                self.enabled = False
                self.listening_toggled.emit(False)
            finally:
                logging.info("System audio listening disabled")

        self._thread = threading.Thread(target=_run, daemon=True)
        # Emitted before starting the thread (not after) so this always
        # happens-before any failure the thread might emit itself — emitting
        # from the caller afterward raced with the thread's own emit(False) on
        # an immediate capture failure, occasionally reporting "on" last.
        self.listening_toggled.emit(True)
        self._thread.start()

    def _stop(self):
        self._stop_event.set()
        self.listening_toggled.emit(False)

    def _resample_to_16k(self, audio, native_rate: int = CAPTURE_SAMPLE_RATE):
        import numpy as np
        if native_rate == SAMPLE_RATE or audio.size == 0:
            return audio
        duration = audio.shape[0] / native_rate
        target_len = max(1, int(duration * SAMPLE_RATE))
        x_old = np.linspace(0, duration, num=audio.shape[0], endpoint=False)
        x_new = np.linspace(0, duration, num=target_len, endpoint=False)
        # np.interp always returns float64, but the whisper model's ONNX VAD
        # filter requires float32 — without this cast it throws at transcribe time.
        return np.interp(x_new, x_old, audio).astype(np.float32)

    def _transcribe(self, frames, native_rate: int = CAPTURE_SAMPLE_RATE):
        if not frames:
            return

        try:
            import numpy as np
            raw = np.concatenate(frames, axis=0).flatten().astype(np.float32)
            audio = self._resample_to_16k(raw, native_rate)
        except Exception as e:
            logging.error(f"Failed to prepare system audio: {e}")
            return

        if audio.size < SAMPLE_RATE * MIN_AUDIO_SECONDS:
            return

        model = self._ensure_model()
        if not model:
            return

        try:
            # See input.py's TRANSCRIBE_LOCK: this can share a WhisperModel instance
            # with VoiceInput (model_provider), and segments is a lazy generator, so
            # the lock has to wrap list(segments) too, not just the transcribe() call.
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
            text = " ".join(
                seg.text.strip() for seg in segments if getattr(seg, "no_speech_prob", 0) < MAX_NO_SPEECH_PROB
            ).strip()
        except Exception as e:
            logging.error(f"System audio transcription error: {e}")
            return

        if not text:
            return

        now = time.monotonic()
        if now - self._last_emit_time < EMIT_COOLDOWN_S:
            logging.debug("System audio transcription suppressed (cooldown).")
            return
        self._last_emit_time = now
        self.audio_transcribed.emit(text)
