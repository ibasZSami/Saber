import json
import logging
from typing import Dict, Any

TOOLS_SCHEMA = [
    {
        "name": "observe_screen",
        "description": "Obtém uma análise da tela atual."
    },
    {
        "name": "translate_screen",
        "description": "Captura a tela, executa OCR e traduz o texto selecionado."
    },
    {
        "name": "open_application",
        "description": "Abre um aplicativo configurado na allowlist (ex: chrome, discord, vscode).",
        "parameters": {"application": "string"}
    },
    {
        "name": "open_url",
        "description": "Abre uma URL no navegador padrão.",
        "parameters": {"url": "string"}
    },
    {
        "name": "search_web",
        "description": "Pesquisa na web por um termo.",
        "parameters": {"query": "string"}
    },
    {
        "name": "remember",
        "description": "Salva uma informação importante na memória de longo prazo.",
        "parameters": {"key": "string", "value": "string"}
    },
    {
        "name": "forget_memory",
        "description": "Remove uma informação da memória.",
        "parameters": {"key": "string"}
    }
]

def parse_ai_response(response_text: str) -> Dict[str, Any]:
    try:
        # Find JSON boundaries
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start != -1 and end != -1:
            json_str = response_text[start:end+1]
            return json.loads(json_str)
    except Exception as e:
        logging.warning(f"Failed to parse AI JSON response: {e}")

    return {
        "speech": response_text,
        "animation": "TALKING",
        "action": "Nenhuma",
        "action_param": ""
    }
