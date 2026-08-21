"""Human-readable Privacy Center summary — FASE Privacy Center. Built from
SilvaState's snapshot (src/core/silva_state.py), which already aggregates
"what's happening right now" from every subsystem. This module's only job
is turning that raw dict into text a user can read in one glance: what
Silva can see, hear, and remember right now, all in one place instead of
scattered across Configurações → Visão/Voz and the Atividade tab."""


def format_privacy_summary(snapshot: dict) -> str:
    vision = snapshot.get("vision", {})
    voice = snapshot.get("voice", {})
    memory = snapshot.get("memory", {})
    desktop = snapshot.get("desktop", {})

    lines = ["O QUE A SILVA VÊ", ""]
    if not vision.get("monitoring_enabled", False) or vision.get("private_mode", True):
        lines.append("- Visão de tela: DESLIGADA (Modo Privado ou monitoramento desativado)")
    else:
        lines.append(f"- Visão de tela: ATIVA (modo {vision.get('mode', '?')})")
    translation_state = vision.get("translation_mode_state")
    if translation_state and translation_state != "OFF":
        lines.append(f"- Modo Tradução: ATIVO ({translation_state}) — captura e traduz o que aparece na tela continuamente")
    lines.append(f"- Janela ativa detectada: {desktop.get('active_window') or 'nenhuma'}")

    lines += ["", "O QUE A SILVA OUVE", ""]
    lines.append(f"- Microfone: {'OUVINDO agora' if voice.get('listening') else 'desligado'}")
    lines.append(f"- Modo mãos-livres: {'ativo' if voice.get('hands_free_enabled') else 'desligado'}")
    lines.append(f"- Áudio do jogo/PC: {'OUVINDO agora' if voice.get('system_audio_listening') else 'desligado'}")

    saved_keys = memory.get("saved_keys", [])
    lines += ["", f"O QUE A SILVA LEMBRA ({memory.get('saved_count', 0)} item(ns))", ""]
    if saved_keys:
        lines.extend(f"- {key}" for key in saved_keys)
    else:
        lines.append("- Nenhuma memória de longo prazo salva.")

    return "\n".join(lines)
