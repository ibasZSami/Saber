"""Controlled terminal execution — FASE 3. This is NOT a shell: only
pre-approved binaries from an explicit allowlist run (empty by default —
see Settings → Terminal), always dispatched via CONFIRM tier one layer up
(src/core/tool_registry.py), arguments passed as a real argv list
(subprocess.run(..., shell=False) — never a shell string), output captured
and size-capped, every run logged via a dedicated event so it's visible in
the Atividade tab regardless of what the generic ACTION_EXECUTED bookkeeping
carries."""

import logging
import shlex
import subprocess

from src.core.event_bus import EventBus, TERMINAL_TOOL_EXECUTED

MAX_OUTPUT_CHARS = 4000
TIMEOUT_SECONDS = 30

# Characters with no legitimate use in an argument to any of these tools —
# subprocess.run(shell=False) already can't interpret them as shell syntax
# (they'd just be a literal, harmless string argument to the binary), but
# rejecting them outright removes any ambiguity rather than relying on that.
_DISALLOWED_ARG_CHARS = ("|", "&", ";", ">", "<", "`", "$")


class TerminalToolManager:
    def __init__(self, allowlist: dict, event_bus: EventBus):
        """allowlist: {name: absolute_path_to_binary} — same shape as the
        app allowlist (src/desktop/permissions.py), managed the same way."""
        self.allowlist = allowlist
        self.event_bus = event_bus

    def run(self, name: str, args: str = "") -> dict:
        name_clean = (name or "").strip().lower()
        binary_path = self.allowlist.get(name_clean)
        if not binary_path:
            return self._finish(name_clean, args, False, "", f'"{name}" não está na allowlist de terminal.')

        try:
            arg_list = shlex.split(args) if args else []
        except ValueError as e:
            return self._finish(name_clean, args, False, "", f"Argumentos inválidos: {e}")

        for token in arg_list:
            if any(ch in token for ch in _DISALLOWED_ARG_CHARS):
                return self._finish(name_clean, args, False, "", "Argumento contém caractere não permitido.")

        try:
            result = subprocess.run(
                [binary_path] + arg_list, capture_output=True, text=True,
                timeout=TIMEOUT_SECONDS, shell=False,
            )
            output = ((result.stdout or "") + (result.stderr or ""))[:MAX_OUTPUT_CHARS]
            return self._finish(name_clean, args, result.returncode == 0, output, None)
        except subprocess.TimeoutExpired:
            return self._finish(name_clean, args, False, "", f"Comando excedeu {TIMEOUT_SECONDS}s e foi cancelado.")
        except Exception as e:
            logging.error(f"Terminal tool '{name}' failed: {e}")
            return self._finish(name_clean, args, False, "", str(e))

    def _finish(self, name: str, args: str, success: bool, output: str, error) -> dict:
        result = {"success": success, "output": output, "error": error}
        self.event_bus.emit(
            TERMINAL_TOOL_EXECUTED, name=name, args=args, success=success, output=output, error=error,
        )
        return result
