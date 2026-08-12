import json
import logging
import re
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

# Narration the model sometimes adds despite the system prompt forbidding it
# (stage directions like "*ele sorri*", "(ri)", "[pensativo]"), which reads
# out loud as literal punctuation/description instead of being silently skipped.
_NARRATION_RE = re.compile(r"\*[^*]*\*|\([^)]*\)|\[[^\]]*\]")


def _sanitize_speech(text: str) -> str:
    stripped = re.sub(r"\s+", " ", _NARRATION_RE.sub(" ", text).replace("*", "")).strip()
    if stripped or not text.strip():
        return stripped
    # The whole reply was wrapped in narration markers (e.g. the model answered
    # entirely inside parentheses) — stripping it would silence a real answer,
    # so fall back to the original text (minus literal asterisks) instead of
    # going quiet on a question the user actually asked.
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def _unescape_json_string(s: str) -> str:
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def parse_ai_response(response_text: str) -> Dict[str, Any]:
    try:
        # Find JSON boundaries
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start != -1 and end != -1:
            json_str = response_text[start:end+1]
            parsed = json.loads(json_str)
            # `.get("speech", "")`'s default only kicks in when the key is absent —
            # a JSON `null` (valid, and something a small model can produce) comes
            # through as None, and str(None) is the non-empty string "None", which
            # would then get spoken/shown as the literal word "None".
            parsed["speech"] = _sanitize_speech(str(parsed.get("speech") or ""))
            return parsed
    except Exception as e:
        logging.warning(f"Failed to parse AI JSON response: {e}")

    # The full object didn't parse — common with smaller/faster models on
    # longer replies (stray quote, trailing comma, etc.) — but the "speech"
    # field itself is usually still intact. Pull it out directly instead of
    # falling through to speaking the raw broken JSON out loud (braces,
    # field names, quotes and all).
    speech_match = re.search(r'"speech"\s*:\s*"((?:[^"\\]|\\.)*)"', response_text)
    if speech_match:
        anim_match = re.search(r'"animation"\s*:\s*"(\w+)"', response_text)
        return {
            "speech": _sanitize_speech(_unescape_json_string(speech_match.group(1))),
            "animation": anim_match.group(1) if anim_match else "TALKING",
            "action": "Nenhuma",
            "action_param": ""
        }

    # Doesn't look like JSON at all — treat it as plain speech (keeps
    # working if a provider ever answers in plain text).
    if "{" not in response_text:
        return {
            "speech": _sanitize_speech(response_text),
            "animation": "TALKING",
            "action": "Nenhuma",
            "action_param": ""
        }

    # Looks like JSON but too broken to salvage even the speech field —
    # better to stay quiet than to read raw JSON syntax out loud.
    logging.warning(f"Could not salvage speech from malformed AI response: {response_text!r}")
    return {
        "speech": "",
        "animation": "CONFUSED",
        "action": "Nenhuma",
        "action_param": ""
    }
