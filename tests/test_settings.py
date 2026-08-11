import json
import os
from unittest.mock import patch

from src.config.settings import Settings


class TestSettings:
    def test_creates_default_config_when_missing(self, tmp_path):
        config_path = tmp_path / "config.json"
        settings = Settings(config_path=str(config_path))

        assert config_path.exists()
        assert settings.get("character_name") == "Saber"

    def test_loads_existing_config_and_merges_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"character_name": "Nyx"}), encoding="utf-8")

        settings = Settings(config_path=str(config_path))

        assert settings.get("character_name") == "Nyx"
        assert settings.get("ai_provider") == "nvidia"

    def test_set_persists_to_disk(self, tmp_path):
        config_path = tmp_path / "config.json"
        settings = Settings(config_path=str(config_path))

        settings.set("character_name", "Nyx")

        reloaded = json.loads(config_path.read_text(encoding="utf-8"))
        assert reloaded["character_name"] == "Nyx"

    def test_corrupted_config_falls_back_to_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text("{not valid json", encoding="utf-8")

        settings = Settings(config_path=str(config_path))

        assert settings.get("character_name") == "Saber"


class TestApiKeyEnvPriority:
    def test_env_var_takes_priority_over_config_file(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"ai_provider": "nvidia", "api_key": "stored-in-file"}), encoding="utf-8")

        with patch.dict(os.environ, {"NVIDIA_API_KEY": "nvapi-from-env"}, clear=False):
            settings = Settings(config_path=str(config_path))
            assert settings.get("api_key") == "nvapi-from-env"

    def test_falls_back_to_config_file_when_env_var_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"ai_provider": "nvidia", "api_key": "stored-in-file"}), encoding="utf-8")

        settings = Settings(config_path=str(config_path))
        assert settings.get("api_key") == "stored-in-file"

    def test_env_var_only_applies_to_matching_provider(self, tmp_path, monkeypatch):
        # load_dotenv() (triggered at settings import time) may have already populated
        # NVIDIA_API_KEY from the project's real .env; clear it so this test only
        # observes the OPENAI_API_KEY var it sets, isolating the provider-match check.
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"ai_provider": "nvidia", "api_key": "stored-in-file"}), encoding="utf-8")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai-env"}, clear=False):
            settings = Settings(config_path=str(config_path))
            assert settings.get("api_key") == "stored-in-file"
