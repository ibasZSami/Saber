import logging
import requests
import json
from typing import Dict, Any, List

class AIProvider:
    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]]) -> str:
        raise NotImplementedError

class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]]) -> str:
        if not self.api_key:
            return json.dumps({
                "speech": "Minha chave de API (OpenAI API Key) ainda não foi configurada. Você pode inseri-la nas Configurações.",
                "animation": "CONFUSED",
                "action": "Nenhuma"
            })

        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": prompt})

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
]

class NvidiaProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "meta/llama-3.1-70b-instruct"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://integrate.api.nvidia.com/v1"

    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]]) -> str:
        if not self.api_key:
            return json.dumps({
                "speech": "Minha chave da NVIDIA API Key não foi inserida. Adicione nas Configurações.",
                "animation": "CONFUSED",
                "action": "Nenhuma"
            })

        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": prompt})

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

    def chat(self, prompt: str, system_prompt: str, history: List[Dict[str, str]]) -> str:
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
