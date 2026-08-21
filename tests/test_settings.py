import json
import os
import sys
from unittest.mock import patch

from src.config.settings import Settings, _compute_project_root


class TestSettings:
    def test_creates_default_config_when_missing(self, tmp_path):
        config_path = tmp_path / "config.json"
        settings = Settings(config_path=str(config_path))

        assert config_path.exists()
        assert settings.get("character_name") == "Silva"
        assert settings.get("whisper_model") == "small"

    def test_default_text_model_is_not_the_vision_model(self, tmp_path):
        """Regression test: a vision-capable model was briefly the default for
        ALL chat, not just screen-related messages, and it was unreliable at
        following the action/JSON format (see orchestrator's dual-provider setup)."""
        settings = Settings(config_path=str(tmp_path / "config.json"))
        assert settings.get("ai_model") != settings.get("ai_vision_model")
        assert "vision" not in settings.get("ai_model")

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

        assert settings.get("character_name") == "Silva"


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


class TestSetApiKey:
    """set_api_key() exists because the wizard/Settings screen used to call
    plain set("api_key", ...), writing the secret into config.json — this
    contradicted the documented design (secrets live only in .env) and meant
    a fresh key never took effect via the env-var path get() prefers."""

    def test_writes_to_env_file_next_to_config_not_config_json(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        config_path = tmp_path / "config.json"
        settings = Settings(config_path=str(config_path))

        settings.set_api_key("nvapi-new-key")

        env_content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "NVIDIA_API_KEY=nvapi-new-key" in env_content
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert "api_key" not in stored

    def test_takes_effect_immediately_without_restart(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        settings = Settings(config_path=str(tmp_path / "config.json"))

        settings.set_api_key("nvapi-live-key")

        assert settings.get("api_key") == "nvapi-live-key"

    def test_updates_existing_env_var_in_place(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        (tmp_path / ".env").write_text("NVIDIA_API_KEY=old-key\nOPENAI_API_KEY=\n", encoding="utf-8")
        settings = Settings(config_path=str(tmp_path / "config.json"))

        settings.set_api_key("new-key")

        lines = (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
        assert "NVIDIA_API_KEY=new-key" in lines
        assert "OPENAI_API_KEY=" in lines

    def test_ignores_blank_value(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        settings = Settings(config_path=str(tmp_path / "config.json"))

        settings.set_api_key("")

        assert not (tmp_path / ".env").exists()

    def test_provider_without_env_mapping_falls_back_to_config(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"ai_provider": "ollama"}), encoding="utf-8")
        settings = Settings(config_path=str(config_path))

        settings.set_api_key("some-key")

        assert not (tmp_path / ".env").exists()
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert stored["api_key"] == "some-key"


class TestComputeProjectRoot:
    """PROJECT_ROOT anchors every shipped-asset/data path in the app — wrong
    in a frozen build and nothing (sprites, plugins, config.json, the memory
    DB) can find its files. See packaging/README.md and the frozen-mode note
    in src/config/settings.py."""

    def test_unfrozen_walks_up_from_this_file_to_the_repo_root(self):
        with patch.object(sys, "frozen", False, create=True):
            root = _compute_project_root()

        assert (root / "main.py").exists()
        assert (root / "extracted_assets").exists()

    def test_frozen_uses_the_directory_containing_the_executable(self, tmp_path):
        fake_exe = tmp_path / "Silva.exe"
        fake_exe.write_text("", encoding="utf-8")

        with patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "executable", str(fake_exe)):
            root = _compute_project_root()

        assert root == tmp_path.resolve()

    def test_frozen_root_is_independent_of_this_source_files_location(self, tmp_path):
        """The frozen branch must never fall through to the __file__ walk-up —
        that would resolve to somewhere inside a PyInstaller _internal folder,
        not the directory the user actually installed Silva into."""
        fake_exe = tmp_path / "nested" / "Silva.exe"
        fake_exe.parent.mkdir()
        fake_exe.write_text("", encoding="utf-8")

        with patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "executable", str(fake_exe)):
            root = _compute_project_root()

        assert root == (tmp_path / "nested").resolve()
        assert "settings.py" not in str(root)
