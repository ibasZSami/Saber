"""Parses one step of the Agent Engine's task loop (FASE 2) — a DIFFERENT
JSON schema from the conversational reply (src/ai/tools.py's
parse_ai_response): no "speech"/"emotion" to say out loud, just a decision
about what to do next. See src/ai/prompts.py's build_agent_system_prompt for
the schema described to the model."""

import json
import logging
from typing import Any, Dict


def parse_agent_response(response_text: str) -> Dict[str, Any]:
    try:
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start != -1 and end != -1:
            parsed = json.loads(response_text[start:end + 1])
            return {
                "thought": str(parsed.get("thought") or ""),
                "done": bool(parsed.get("done", False)),
                "result": parsed.get("result"),
                "action": parsed.get("action") or "Nenhuma",
                "action_param": parsed.get("action_param", ""),
            }
    except Exception as e:
        logging.warning(f"Failed to parse agent JSON response: {e}")

    # Malformed output must END the task with a clear failure, never loop
    # blindly on something that couldn't be understood — see
    # TaskManager/AgentEngine's step-limit safety net for the other half of
    # this guarantee (a well-formed-but-stuck loop still gets cut off).
    return {
        "thought": "",
        "done": True,
        "result": "Não consegui interpretar a resposta da IA para continuar a tarefa.",
        "action": "Nenhuma",
        "action_param": "",
    }
