import logging
import threading
from PySide6.QtCore import QObject, Signal

class VoiceInput(QObject):
    speech_recognized = Signal(str)

    def __init__(self):
        super().__init__()
        self.is_listening = False

    def start_listening(self):
        logging.info("VoiceInput listening started (Push-to-Talk F8 pressed)")
        self.is_listening = True

    def stop_listening(self):
        logging.info("VoiceInput listening stopped")
        self.is_listening = False
        # Dummy recognition trigger for testing audio pipeline
        # Replace with faster-whisper stream transcription if model downloaded
