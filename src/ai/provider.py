import logging
import requests
import json
from typing import Dict, Any, List

def _build_user_message(prompt: str, image_base64: str = None) -> Any:
    """Builds a plain-text or multimodal user message depending on whether an image is attached."""
    if not image_base64:
        return prompt
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
    ]

class AIProvider:
    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]], image_base64: str = None) -> str:
        raise NotImplementedError

# Prefixes of OpenAI models known to accept image inputs
OPENAI_VISION_PREFIXES = ("gpt-4o", "gpt-4.1", "gpt-4-turbo", "o1", "o3", "o4", "gpt-5")

class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def supports_vision(self) -> bool:
        return self.model.startswith(OPENAI_VISION_PREFIXES)

    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]], image_base64: str = None) -> str:
        if not self.api_key:
            return json.dumps({
                "speech": "Minha chave de API (OpenAI API Key) ainda não foi configurada. Você pode inseri-la nas Configurações.",
                "animation": "CONFUSED",
                "action": "Nenhuma"
            })

        if image_base64 and not self.supports_vision():
            logging.debug(f"Model {self.model} does not support vision; sending text-only.")
            image_base64 = None

        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": _build_user_message(prompt, image_base64)})

            res = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7
            )
            return res.choices[0].message.content
        except Exception as e:
            logging.error(f"OpenAI Error: {e}")
            return json.dumps({
                "speech": f"Tive um problema ao me conectar com a IA: {str(e)}",
                "animation": "SAD",
                "action": "Nenhuma"
            })

# Modelos disponíveis na NVIDIA NIM (https://build.nvidia.com)
NVIDIA_MODELS = [
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mixtral-8x7b-instruct-v0.1",
    "microsoft/phi-3-mini-128k-instruct",
    "google/gemma-2-27b-it",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
]

# NVIDIA NIM models known to accept image inputs (needed for real screen vision)
NVIDIA_VISION_MODELS = {
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "microsoft/phi-3.5-vision-instruct",
}

class NvidiaProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "meta/llama-3.2-11b-vision-instruct"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://integrate.api.nvidia.com/v1"

    def supports_vision(self) -> bool:
        return self.model in NVIDIA_VISION_MODELS

    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]], image_base64: str = None) -> str:
        if not self.api_key:
            return json.dumps({
                "speech": "Minha chave da NVIDIA API Key não foi inserida. Adicione nas Configurações.",
                "animation": "CONFUSED",
                "action": "Nenhuma"
            })

        if image_base64 and not self.supports_vision():
            logging.debug(f"Model {self.model} does not support vision; sending text-only.")
            image_base64 = None

        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": _build_user_message(prompt, image_base64)})

            res = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            return res.choices[0].message.content
        except Exception as e:
            logging.error(f"NVIDIA API Error: {e}")
            return json.dumps({
                "speech": f"Erro na conexão com NVIDIA API: {str(e)}",
                "animation": "SAD",
                "action": "Nenhuma"
            })


class OllamaProvider(AIProvider):
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3"):
        self.host = host
        self.model = model

    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]], image_base64: str = None) -> str:
        if image_base64:
            logging.debug("Ollama provider does not support vision yet; sending text-only.")
        try:
            url = f"{self.host}/api/chat"
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False
            }
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data.get("message", {}).get("content", "")
            return json.dumps({"speech": "Erro ao conectar com Ollama.", "animation": "CONFUSED"})
        except Exception as e:
            logging.error(f"Ollama Error: {e}")
            return json.dumps({"speech": f"Erro Ollama: {str(e)}", "animation": "SAD"})
