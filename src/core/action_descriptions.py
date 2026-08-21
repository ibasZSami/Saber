"""Human-readable descriptions of CONFIRM-tier tool calls, shown in the real
confirmation dialog (src/ui/confirmation_dialog.py) before the action runs.
Kept as a pure function — no Qt import — so it's trivially unit-testable and
reusable if the description is ever needed somewhere other than a dialog
(e.g. a future Activity Log entry, FASE 7)."""


def describe_action(action: str, action_param) -> str:
    if action == "open_application":
        return f'Silva quer abrir o aplicativo "{action_param}".'
    if action == "close_application":
        return f'Silva quer fechar o aplicativo "{action_param}".'
    if action == "open_url":
        return f"Silva quer abrir esta página no navegador:\n{action_param}"
    if action == "set_app_volume":
        if isinstance(action_param, dict):
            app = action_param.get("application", "?")
            level = action_param.get("level", "?")
            return f'Silva quer ajustar o volume de "{app}" para {level}%.'
        return "Silva quer ajustar o volume de um aplicativo."
    # Fallback for any future CONFIRM-tier tool that doesn't get bespoke copy
    # here yet — still informative, never blank.
    return f'Silva quer executar a ação "{action}" ({action_param!r}).'
