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
    if action == "mouse_click":
        if isinstance(action_param, dict):
            return f'Silva quer clicar na posição ({action_param.get("x", "?")}, {action_param.get("y", "?")}) da tela.'
        return "Silva quer clicar em algum lugar da tela."
    if action == "mouse_move":
        if isinstance(action_param, dict):
            return f'Silva quer mover o mouse até ({action_param.get("x", "?")}, {action_param.get("y", "?")}).'
        return "Silva quer mover o mouse."
    if action == "type_text":
        text = action_param.get("text", "") if isinstance(action_param, dict) else str(action_param)
        return f'Silva quer digitar: "{text}"'
    if action == "press_key":
        key = action_param.get("key", "?") if isinstance(action_param, dict) else str(action_param)
        return f'Silva quer pressionar a tecla "{key}".'
    if action == "run_terminal_tool":
        if isinstance(action_param, dict):
            name = action_param.get("name", "?")
            args = action_param.get("args", "")
            return f'Silva quer rodar "{name}"{f" com argumentos: {args}" if args else ""} no terminal.'
        return "Silva quer rodar uma ferramenta de terminal."
    if action == "browser_navigate":
        url = action_param.get("url", "?") if isinstance(action_param, dict) else str(action_param)
        return f"Silva quer abrir esta página no navegador controlado:\n{url}"
    if action == "browser_click":
        target = action_param.get("target", "?") if isinstance(action_param, dict) else str(action_param)
        return f'Silva quer clicar em "{target}" na página aberta.'
    if action == "browser_type":
        if isinstance(action_param, dict):
            target = action_param.get("target", "?")
            text = action_param.get("text", "")
            return f'Silva quer digitar "{text}" em "{target}" na página aberta.'
        return "Silva quer digitar algo na página aberta."
    if action == "index_folder":
        path = action_param.get("path", "?") if isinstance(action_param, dict) else str(action_param)
        return f'Silva quer ler os arquivos de texto/código desta pasta pra poder buscar neles depois:\n{path}'
    # Fallback for any future CONFIRM-tier tool that doesn't get bespoke copy
    # here yet — still informative, never blank.
    return f'Silva quer executar a ação "{action}" ({action_param!r}).'
