"""Example plugin — adds a harmless "roll_dice" tool, mostly to prove the
plugin mechanism works and give a copy-paste starting point. See README.md
in this folder for the full guide.

Ignored by PluginManager unless Configurações -> Agente -> Permitir
plugins is turned on (off by default)."""

import random

from src.core.tool_registry import PermissionTier, ToolSpec


def _roll_dice(action_param):
    sides = 6
    if isinstance(action_param, dict) and action_param.get("sides"):
        try:
            sides = max(2, min(1000, int(action_param["sides"])))
        except (TypeError, ValueError):
            sides = 6
    result = random.randint(1, sides)
    # Returning (bool, str) instead of a bare bool surfaces the actual roll
    # as "detail" through AgentCore.execute_with_detail — same pattern
    # observe_screen/run_terminal_tool use for a result worth seeing.
    return True, f"Rolou {result} (dado de {sides} lados)."


def register(context):
    context.register_tool(ToolSpec(
        name="roll_dice",
        tier=PermissionTier.SAFE,
        description="Rola um dado (6 lados por padrão) e diz o resultado.",
        dispatch=_roll_dice,
        parameters={"sides": "number (opcional, padrão 6)"},
    ))
