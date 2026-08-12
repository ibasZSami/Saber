import os
import json
import logging
from pathlib import Path

# Ship-with-repo sprite copy, so a fresh clone works without depending on an
# external personal folder (e.g. a user's Downloads directory) that may move or be deleted.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ASSETS_PATH = str(PROJECT_ROOT / "extracted_assets" / "silva")

try:
    from dotenv import load_dotenv
    # Explicit absolute path — load_dotenv() with no argument only searches the
    # current working directory upward, which isn't the project root when Silva
    # is launched from the Windows autostart Run key (CWD is whatever Explorer/
    # the shell set it to, not necessarily this project's folder).
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

ENV_KEY_BY_PROVIDER = {
    "nvidia": "NVIDIA_API_KEY",
    "openai": "OPENAI_API_KEY",
}

DEFAULT_CONFIG_PATH = str(PROJECT_ROOT / "config.json")

DEFAULT_CONFIG = {
    "character_name": "Silva",
    "ai_provider": "nvidia",
    "ai_model": "meta/llama-3.1-8b-instruct",
    "ai_model_complex": "meta/llama-3.1-70b-instruct",
    "ai_vision_model": "meta/llama-3.2-11b-vision-instruct",
    "api_key": "",
    "voice_provider": "edge_tts",
    "voice": "pt-BR-AntonioNeural",
    "voice_speed": 1.05,
    "voice_volume": 1.0,
    "voice_pitch": "+20Hz",
    "microphone_enabled": False,
    "whisper_model": "small",
    "screen_monitoring_enabled": False,
    "screen_interval_seconds": 2.0,
    "spontaneous_talk_enabled": True,
    "autostart_enabled": True,
    "click_through": False,
    "always_on_top": True,
    "window_margin_x": 40,
    "window_margin_y": 40,
    "scale": 1.0,
    "language": "pt-BR",
    "private_mode": True,
    "assets_path": DEFAULT_ASSETS_PATH,
    "allowlist": {
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "discord": r"C:\Users\ribas\AppData\Local\Discord\Update.exe --processStart Discord.exe",
        "vscode": "code",
        "notepad": "notepad.exe"
    }
}

class Settings:
    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else Path(DEFAULT_CONFIG_PATH)
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as e:
                logging.error(f"Error loading config.json: {e}")
        else:
            self.save()

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error saving config.json: {e}")

    def get(self, key, default=None):
        if key == "api_key":
            env_var = ENV_KEY_BY_PROVIDER.get(self.data.get("ai_provider", "nvidia"))
            env_value = os.environ.get(env_var) if env_var else None
            if env_value:
                return env_value
        return self.data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()
