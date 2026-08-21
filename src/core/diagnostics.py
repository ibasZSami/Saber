"""Local, offline health check ("SILVA DIAGNOSTICS") — answers "is everything
this app depends on actually working?" in one place, so a user hitting a
problem (no mic input, screen translation not working, autostart not
registered) has somewhere to look besides the log file.

Every check function is defensive on its own AND wrapped again in
run_diagnostics() — a bug in one check must turn into a FAIL result for just
that check, never crash the whole report. Nothing here ever includes a
secret: the API key check reports presence/provider only, never the key
value itself (see _check_api_key)."""

import os
from dataclasses import dataclass
from enum import Enum
from typing import List


class CheckStatus(str, Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: CheckStatus
    detail: str = ""


def _check_python() -> DiagnosticCheck:
    import sys
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        return DiagnosticCheck("Python", CheckStatus.OK, version)
    return DiagnosticCheck("Python", CheckStatus.WARN, f"{version} — Silva pede 3.11+")


def _check_qt() -> DiagnosticCheck:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        return DiagnosticCheck("Qt", CheckStatus.FAIL, f"PySide6 não encontrado: {e}")
    if QApplication.instance() is None:
        return DiagnosticCheck("Qt", CheckStatus.WARN, "PySide6 carregado, mas nenhuma QApplication ativa")
    return DiagnosticCheck("Qt", CheckStatus.OK, "PySide6 carregado e QApplication ativa")


def _query_audio_devices():
    import sounddevice as sd
    return sd.query_devices()


def _check_audio_input() -> DiagnosticCheck:
    try:
        devices = _query_audio_devices()
    except Exception as e:
        return DiagnosticCheck("Audio input", CheckStatus.FAIL, f"Erro ao consultar dispositivos: {e}")
    if any(d.get("max_input_channels", 0) > 0 for d in devices):
        return DiagnosticCheck("Audio input", CheckStatus.OK, "Microfone detectado")
    return DiagnosticCheck("Audio input", CheckStatus.WARN, "Nenhum dispositivo de entrada de áudio encontrado")


def _check_audio_output() -> DiagnosticCheck:
    try:
        devices = _query_audio_devices()
    except Exception as e:
        return DiagnosticCheck("Audio output", CheckStatus.FAIL, f"Erro ao consultar dispositivos: {e}")
    if any(d.get("max_output_channels", 0) > 0 for d in devices):
        return DiagnosticCheck("Audio output", CheckStatus.OK, "Saída de áudio detectada")
    return DiagnosticCheck("Audio output", CheckStatus.WARN, "Nenhum dispositivo de saída de áudio encontrado")


def _check_whisper() -> DiagnosticCheck:
    try:
        import faster_whisper  # noqa: F401
    except ImportError as e:
        return DiagnosticCheck("Whisper", CheckStatus.FAIL, f"faster-whisper não instalado: {e}")
    return DiagnosticCheck("Whisper", CheckStatus.OK, "faster-whisper instalado")


def _check_tesseract() -> DiagnosticCheck:
    from src.vision.ocr import TesseractOCRProvider
    if TesseractOCRProvider().available:
        return DiagnosticCheck("Tesseract", CheckStatus.OK, "Binário do Tesseract encontrado")
    return DiagnosticCheck(
        "Tesseract", CheckStatus.WARN,
        "Não encontrado — tradução de tela não vai funcionar "
        "(winget install --id UB-Mannheim.TesseractOCR -e)",
    )


def _check_api_key(settings) -> DiagnosticCheck:
    provider = settings.get("ai_provider", "nvidia")
    if provider == "ollama":
        return DiagnosticCheck("API", CheckStatus.OK, "Provedor Ollama (local, sem chave necessária)")
    if settings.get("api_key", ""):
        return DiagnosticCheck("API", CheckStatus.OK, f"Chave configurada para {provider}")
    return DiagnosticCheck("API", CheckStatus.FAIL, f"Nenhuma chave de API configurada para {provider}")


def _check_assets(settings) -> DiagnosticCheck:
    assets_path = settings.get("assets_path", "")
    if not assets_path or not os.path.isdir(assets_path):
        return DiagnosticCheck("Assets", CheckStatus.FAIL, f"Pasta de sprites não encontrada: {assets_path}")
    sprite_count = sum(1 for f in os.listdir(assets_path) if f.lower().endswith(".png"))
    if sprite_count == 0:
        return DiagnosticCheck("Assets", CheckStatus.FAIL, f"Pasta existe mas sem nenhum sprite .png: {assets_path}")
    return DiagnosticCheck("Assets", CheckStatus.OK, f"{sprite_count} sprite(s) encontrado(s)")


def _check_configuration(settings) -> DiagnosticCheck:
    settings.get("character_name")  # touches the loaded config; raises if truly broken
    return DiagnosticCheck("Configuration", CheckStatus.OK, str(getattr(settings, "config_path", "")))


def _check_permissions(settings) -> DiagnosticCheck:
    allowlist = settings.get("allowlist", {})
    if allowlist:
        return DiagnosticCheck("Permissions", CheckStatus.OK, f"{len(allowlist)} app(s) na allowlist")
    return DiagnosticCheck(
        "Permissions", CheckStatus.WARN,
        "Nenhum app na allowlist — abrir/fechar apps por comando não vai funcionar "
        "até adicionar em Configurações → Aplicativos",
    )


def _check_autostart() -> DiagnosticCheck:
    from src.core import autostart
    if autostart.is_enabled():
        return DiagnosticCheck("Autostart", CheckStatus.OK, "Registrado para iniciar com o Windows")
    return DiagnosticCheck("Autostart", CheckStatus.WARN, "Não registrado para iniciar com o Windows")


# (name, callable) — callables taking `settings` are called with it; the
# others take no arguments. Order matches the phase spec's example list.
_CHECKS = [
    ("Python", lambda settings: _check_python()),
    ("Qt", lambda settings: _check_qt()),
    ("Audio input", lambda settings: _check_audio_input()),
    ("Audio output", lambda settings: _check_audio_output()),
    ("Whisper", lambda settings: _check_whisper()),
    ("Tesseract", lambda settings: _check_tesseract()),
    ("API", _check_api_key),
    ("Assets", _check_assets),
    ("Configuration", _check_configuration),
    ("Permissions", _check_permissions),
    ("Autostart", lambda settings: _check_autostart()),
]


def run_diagnostics(settings) -> List[DiagnosticCheck]:
    results = []
    for name, check_fn in _CHECKS:
        try:
            results.append(check_fn(settings))
        except Exception as e:
            # A bug in one check (or an unexpected environment quirk) must
            # not take the rest of the report down with it.
            results.append(DiagnosticCheck(name, CheckStatus.FAIL, f"Erro ao verificar: {e}"))
    return results


_STATUS_SYMBOL = {CheckStatus.OK: "✓", CheckStatus.WARN: "⚠", CheckStatus.FAIL: "✗"}


def format_report(checks: List[DiagnosticCheck]) -> str:
    """Plain text, safe to show in a UI text box or save to a file — see
    settings_window.py's Diagnóstico tab. Never includes secrets: every
    check's own detail text is already secret-free by construction."""
    lines = ["SILVA DIAGNOSTICS", ""]
    for check in checks:
        line = f"{_STATUS_SYMBOL[check.status]} {check.name}"
        if check.detail:
            line += f" — {check.detail}"
        lines.append(line)
    return "\n".join(lines)
