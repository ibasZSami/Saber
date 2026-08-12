from typing import List, Optional


class SpeechSegmenter:
    """Energy-based voice-activity segmentation: feed it one audio chunk (plus its
    RMS and the current monotonic time) at a time, and it tells you when a
    complete utterance is ready to transcribe.

    Shared by VoiceInput's hands-free mode (push-driven, via a mic callback) and
    SystemAudioListener (pull-driven, via a polling loop) — the two previously had
    near-identical, independently-tuned copies of this state machine, which meant
    a silence/timeout tuning fix had to be applied twice. The scales differ (mic
    is raw int16 RMS, system audio is normalized float32 RMS), so `rms_threshold`
    stays a per-instance parameter rather than a shared constant.
    """

    def __init__(self, rms_threshold: float, silence_duration_s: float, max_utterance_s: float):
        self.rms_threshold = rms_threshold
        self.silence_duration_s = silence_duration_s
        self.max_utterance_s = max_utterance_s
        self._buffer: List = []
        self._speaking = False
        self._silence_start: Optional[float] = None
        self._speech_start: Optional[float] = None

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def push(self, chunk, rms: float, now: float) -> Optional[List]:
        """Feed one chunk + its RMS + `time.monotonic()`. Returns the completed
        utterance (list of chunks, oldest first) once silence or the max-duration
        timeout ends it; returns None otherwise (including while still speaking)."""
        if rms > self.rms_threshold:
            if not self._speaking:
                self._speaking = True
                self._speech_start = now
                self._buffer = []
            self._silence_start = None
            self._buffer.append(chunk)
            return None

        if not self._speaking:
            return None

        self._buffer.append(chunk)
        if self._silence_start is None:
            self._silence_start = now

        finished_by_silence = (now - self._silence_start) >= self.silence_duration_s
        finished_by_timeout = (now - self._speech_start) >= self.max_utterance_s
        if finished_by_silence or finished_by_timeout:
            self._speaking = False
            utterance, self._buffer = self._buffer, []
            return utterance
        return None
