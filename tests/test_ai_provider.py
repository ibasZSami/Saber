import json
from unittest.mock import MagicMock, patch

from src.ai.provider import OpenAIProvider, NvidiaProvider, OllamaProvider, _build_user_message


def _mock_openai_response(text):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=text))]
    return resp


class TestBuildUserMessage:
    def test_text_only_without_image(self):
        assert _build_user_message("oi", None) == "oi"

    def test_multimodal_with_image(self):
        result = _build_user_message("oi", "base64data")
        assert result[0] == {"type": "text", "text": "oi"}
        assert result[1]["image_url"]["url"] == "data:image/jpeg;base64,base64data"


class TestOpenAIProvider:
    def test_supports_vision_true_for_gpt4o(self):
        assert OpenAIProvider(api_key="x", model="gpt-4o-mini").supports_vision()

    def test_supports_vision_false_for_gpt35(self):
        assert not OpenAIProvider(api_key="x", model="gpt-3.5-turbo").supports_vision()

    def test_chat_without_api_key_returns_friendly_json(self):
        provider = OpenAIProvider(api_key="")
        raw = provider.chat("oi", "system", [])
        data = json.loads(raw)
        assert data["action"] == "Nenhuma"
        assert "API" in data["speech"]

    @patch("openai.OpenAI")
    def test_chat_drops_image_for_non_vision_model(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response("oi resposta")
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider(api_key="sk-test", model="gpt-3.5-turbo")
        provider.chat("prompt", "system", [], image_base64="fakeimage")

        sent_messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert sent_messages[-1]["content"] == "prompt"

    @patch("openai.OpenAI")
    def test_chat_attaches_image_for_vision_model(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response("vejo a tela")
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")
        result = provider.chat("prompt", "system", [], image_base64="fakeimage")

        sent_messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert isinstance(sent_messages[-1]["content"], list)
        assert result == "vejo a tela"

    @patch("openai.OpenAI")
    def test_chat_handles_api_error_gracefully(self, mock_openai_cls):
        mock_openai_cls.side_effect = RuntimeError("boom")
        provider = OpenAIProvider(api_key="sk-test")
        raw = provider.chat("oi", "system", [])
        data = json.loads(raw)
        assert data["emotion"] == "SAD"


class TestNvidiaProvider:
    def test_supports_vision_true_for_known_model(self):
        assert NvidiaProvider(api_key="x", model="meta/llama-3.2-11b-vision-instruct").supports_vision()

    def test_supports_vision_false_for_text_model(self):
        assert not NvidiaProvider(api_key="x", model="meta/llama-3.1-70b-instruct").supports_vision()

    def test_chat_without_api_key(self):
        provider = NvidiaProvider(api_key="")
        raw = provider.chat("oi", "system", [])
        data = json.loads(raw)
        assert "NVIDIA" in data["speech"]

    @patch("openai.OpenAI")
    def test_chat_uses_nvidia_base_url(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response("ok")
        mock_openai_cls.return_value = mock_client

        provider = NvidiaProvider(api_key="nvapi-test", model="meta/llama-3.2-11b-vision-instruct")
        provider.chat("prompt", "system", [], image_base64="img")

        assert mock_openai_cls.call_args.kwargs["base_url"] == "https://integrate.api.nvidia.com/v1"

    @patch("openai.OpenAI")
    def test_chat_drops_image_for_non_vision_model(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response("ok")
        mock_openai_cls.return_value = mock_client

        provider = NvidiaProvider(api_key="nvapi-test", model="meta/llama-3.1-70b-instruct")
        provider.chat("prompt", "system", [], image_base64="img")

        sent_messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert sent_messages[-1]["content"] == "prompt"


class TestOllamaProvider:
    @patch("requests.post")
    def test_chat_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"message": {"content": "oi"}})
        provider = OllamaProvider()
        assert provider.chat("prompt", "system", []) == "oi"

    @patch("requests.post")
    def test_chat_with_image_ignores_it_without_crashing(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"message": {"content": "oi"}})
        provider = OllamaProvider()
        assert provider.chat("prompt", "system", [], image_base64="fakeimage") == "oi"

    @patch("requests.post")
    def test_chat_non_200_returns_error_json(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        provider = OllamaProvider()
        raw = provider.chat("prompt", "system", [])
        data = json.loads(raw)
        assert "Ollama" in data["speech"]

    @patch("requests.post", side_effect=ConnectionError("offline"))
    def test_chat_connection_error(self, mock_post):
        provider = OllamaProvider()
        raw = provider.chat("prompt", "system", [])
        data = json.loads(raw)
        assert data["emotion"] == "SAD"
