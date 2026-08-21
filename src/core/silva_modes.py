"""Modos do Silva — named presets that adjust several settings/live state at
once instead of toggling each one by hand. No new capability: every effect
here already exists as its own setting or method (screen_monitoring_enabled/
private_mode via set_full_vision, microphone_enabled, spontaneous_talk_enabled,
nerd_mode_enabled) — this is just a one-click way to reach a combination of
them a user would otherwise set individually."""

from typing import Dict, Optional

# Each preset lists only the settings it actually cares about — a key
# absent from a preset is left exactly as it was, not reset to some
# default. "screen_monitoring_enabled" here means "should vision be on",
# applied via CompanionOrchestrator.set_full_vision (which also derives
# private_mode from it and live-starts/stops the monitoring timer).
SILVA_MODES: Dict[str, Dict[str, bool]] = {
    "silencioso": {
        "spontaneous_talk_enabled": False,
        "nerd_mode_enabled": False,
    },
    "trabalho": {
        "microphone_enabled": True,
        "screen_monitoring_enabled": False,
        "spontaneous_talk_enabled": False,
        "nerd_mode_enabled": False,
    },
    "companhia": {
        "microphone_enabled": True,
        "screen_monitoring_enabled": True,
        "spontaneous_talk_enabled": True,
        "nerd_mode_enabled": False,
    },
    "foco": {
        "microphone_enabled": False,
        "screen_monitoring_enabled": False,
        "spontaneous_talk_enabled": False,
        "nerd_mode_enabled": False,
    },
    "privacidade": {
        "microphone_enabled": False,
        "screen_monitoring_enabled": False,
        "spontaneous_talk_enabled": False,
        "nerd_mode_enabled": False,
    },
    "jogo": {
        "microphone_enabled": True,
        "screen_monitoring_enabled": True,
        "spontaneous_talk_enabled": True,
        "nerd_mode_enabled": True,
    },
}

MODE_DESCRIPTIONS: Dict[str, str] = {
    "silencioso": "Não fala por conta própria, mas continua ouvindo e respondendo quando chamada.",
    "trabalho": "Sem comentários espontâneos, sem ver a tela — microfone disponível pra comandos.",
    "companhia": "Conversa e comenta livremente, como numa chamada — microfone e visão ativos.",
    "foco": "Silêncio total: sem microfone, sem visão, só chat de texto.",
    "privacidade": "Desliga tudo agora — microfone, visão, e para qualquer captura contínua já em andamento.",
    "jogo": "Comenta o jogo, mais proativa — microfone, visão e Modo Nerd ativos.",
}

# "microphone_enabled" has no live on/off switch today (only read once at
# startup — see CompanionOrchestrator.__init__) — a mode preset still
# writes it to Settings for consistency, but the mic itself only reflects
# the change after a restart, same limitation the Voz tab's whisper_model
# combo already has.
MIC_REQUIRES_RESTART = True


def is_valid_mode(name: str) -> bool:
    return name in SILVA_MODES


def get_preset(name: str) -> Optional[Dict[str, bool]]:
    return SILVA_MODES.get(name)
