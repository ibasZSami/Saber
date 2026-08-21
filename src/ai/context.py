
class ContextManager:
    def __init__(self):
        self.screen_context = {}
        self.app_context = {}

    def set_screen_context(self, context: dict):
        self.screen_context = context

    def set_app_context(self, context: dict):
        self.app_context = context

    def build_prompt_context(self, memories: dict, user_text: str, vision_enabled: bool = False) -> str:
        ctx_lines = []

        if self.app_context:
            ctx_lines.append(f"[Janela Ativa: {self.app_context.get('window_title', 'Desconhecida')} | Categoria: {self.app_context.get('category', 'geral')}]")

        if vision_enabled:
            ctx_lines.append("[Visão de Tela: Ativada — uma captura de tela atual está anexada a esta mensagem]")
        else:
            ctx_lines.append("[Visão de Tela: Desativada pelo usuário]")

        if memories:
            mem_str = ", ".join([f"{k}: {v}" for k, v in memories.items()])
            ctx_lines.append(f"[Memórias salvas: {mem_str}]")

        ctx_str = "\n".join(ctx_lines)
        return f"{ctx_str}\n\n[Mensagem do Usuário]: {user_text}"
