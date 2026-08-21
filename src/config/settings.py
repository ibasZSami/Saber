import os
import sys
import json
import logging
from pathlib import Path

def _compute_project_root() -> Path:
    """Ship-with-repo sprite copy, so a fresh clone works without depending on
    an external personal folder (e.g. a user's Downloads directory) that may
    move or be deleted.

    A PyInstaller-frozen build has no `src/` tree to walk up from — __file__
    resolves to a path inside the bundled _internal folder, three parents up
    from which is NOT the install directory. sys.frozen + sys.executable's
    own folder is the correct anchor in that case; the source-tree walk-up is
    only valid unfrozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _compute_project_root()
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
    "nerd_mode_enabled": False,
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

    def set_api_key(self, value: str):
        """Writes the API key to .env (keyed by the currently selected
        provider) instead of config.json. get() already prefers the env var
        over self.data["api_key"] when reading, but until now nothing ever
        wrote there — the wizard and Settings screen both called set("api_key", ...),
        putting the secret in config.json, contradicting the documented
        design (secrets live only in .env). Also updates os.environ directly
        so the change takes effect in this already-running process without a
        restart, and clears any leftover plaintext copy from config.json."""
        if not value:
            return
        provider = self.data.get("ai_provider", "nvidia")
        env_var = ENV_KEY_BY_PROVIDER.get(provider)
        if not env_var:
            # Providers with no known env var (e.g. ollama, which needs no
            # key) have nowhere to persist it — fall back to the old behavior
            # rather than silently discarding what the user typed.
            self.set("api_key", value)
            return
        os.environ[env_var] = value
        self._write_env_var(env_var, value)
        self.data.pop("api_key", None)
        self.save()

    def _write_env_var(self, key: str, value: str):
        # Next to config.json, not the hardcoded project root — so a Settings
        # instance pointed at a tmp_path config (as tests do) writes its own
        # isolated .env instead of clobbering the real project's .env.
        env_path = self.config_path.parent / ".env"
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
