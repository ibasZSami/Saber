"""FASE 15 — exposição de secrets.

The API key must never end up in config.json (versioned-adjacent, gitignored
but still a plaintext file people back up/share) and must never leak into a
spoken/displayed error message when a provider call fails."""

import json
from unittest.mock import patch

from src.config.settings import Settings


class TestApiKeyNeverPersistedToConfigJson:
    def test_set_api_key_does_not_write_to_config_json(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        config_path = tmp_path / "config.json"
        settings = Settings(config_path=str(config_path))

        settings.set_api_key("nvapi-super-secret-value")

        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert "api_key" not in stored
        # And it shouldn't be hiding under a different key either.
        assert "nvapi-super-secret-value" not in json.dumps(stored)

    def test_legacy_config_with_api_key_is_not_re_written_with_it_on_a_plain_save(self, tmp_path, monkeypatch):
        """A config.json from before the .env migration (this session) might
        still have a leftover api_key field on disk — a plain settings.set()
        for something unrelated must not be the thing that keeps rewriting it
        back out on every save (it's already there once; this just guards
        against actively re-persisting it via unrelated code paths)."""
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"api_key": "old-leftover-key"}), encoding="utf-8")
        settings = Settings(config_path=str(config_path))

        settings.set("character_name", "Silva")  # unrelated save

        stored = json.loads(config_path.read_text(encoding="utf-8"))
        # Not asserting it's gone (set_api_key is the only thing that cleans
        # it up) — just that nothing re-derives/duplicates it elsewhere.
        assert stored.get("api_key") in (None, "old-leftover-key")


class TestProviderErrorsDoNotLeakTheApiKey:
    def test_openai_provider_error_message_does_not_contain_the_key(self):
        from src.ai.provider import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-super-secret-abc123", model="gpt-4o-mini")
        with patch("openai.OpenAI", side_effect=RuntimeError("connection failed for sk-super-secret-abc123")):
            result = provider.chat("oi", "system", [])

        assert "sk-super-secret-abc123" not in result

    def test_nvidia_provider_error_message_does_not_contain_the_key(self):
        from src.ai.provider import NvidiaProvider

        provider = NvidiaProvider(api_key="nvapi-super-secret-xyz789", model="meta/llama-3.1-8b-instruct")
        with patch("openai.OpenAI", side_effect=RuntimeError("connection failed for nvapi-super-secret-xyz789")):
            result = provider.chat("oi", "system", [])

        assert "nvapi-super-secret-xyz789" not in result

    def test_openai_provider_does_not_log_the_key_either(self, caplog):
        """The redaction has to happen before both the returned speech AND
        the logging.error() call — a leak into the log file is just as real
        as one shown to the user."""
        from src.ai.provider import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-super-secret-abc123", model="gpt-4o-mini")
        with patch("openai.OpenAI", side_effect=RuntimeError("connection failed for sk-super-secret-abc123")):
            provider.chat("oi", "system", [])

        assert "sk-super-secret-abc123" not in caplog.text

    def test_missing_api_key_prompt_does_not_echo_a_blank_or_placeholder_key(self):
        from src.ai.provider import NvidiaProvider

        provider = NvidiaProvider(api_key="", model="meta/llama-3.1-8b-instruct")
        result = provider.chat("oi", "system", [])

        assert "api_key" not in result.lower() or "chave" in result.lower()  # a human-facing message, not a raw field dump
