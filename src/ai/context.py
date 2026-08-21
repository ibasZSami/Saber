import time

# FASE 11: a screen_context reading older than this is never described as
# current — the prompt says explicitly that nothing recent is available
# instead of quietly reusing a stale reading. Matches the vision buffer's own
# TTL (src/vision/continuous_vision.py) so "recent" means the same thing in
# both places, without importing vision internals into this module.
SCREEN_CONTEXT_STALE_AFTER_SECONDS = 30.0


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

        # FASE 11: structured, recency-labeled screen context — previously
        # this was a bare on/off line with no way to say "that reading is old,
        # don't treat it as what's on screen right now." Only shown when a
        # timestamp exists (set by CompanionOrchestrator._check_screen_and_app,
        # i.e. some vision mode is active) — independent of whether a live
        # image is attached to *this* message.
        timestamp = self.screen_context.get("timestamp")
        if timestamp is not None:
            age = time.time() - timestamp
            if age <= SCREEN_CONTEXT_STALE_AFTER_SECONDS:
                title = self.screen_context.get("window_title") or "Desconhecida"
                category = self.screen_context.get("category") or "geral"
                changed_note = ", mudou recentemente" if self.screen_context.get("changed") else ""
                ctx_lines.append(f'[Contexto de tela (há {int(age)}s): janela "{title}" ({category}){changed_note}]')
            else:
                ctx_lines.append("[Contexto de tela: nenhuma leitura recente disponível — não presuma o que está na tela]")

        if vision_enabled:
            ctx_lines.append("[Visão de Tela: Ativada — uma captura de tela atual está anexada a esta mensagem]")
        else:
            ctx_lines.append("[Visão de Tela: Desativada pelo usuário]")

        if memories:
            mem_str = ", ".join([f"{k}: {v}" for k, v in memories.items()])
            ctx_lines.append(f"[Memórias salvas: {mem_str}]")

        ctx_str = "\n".join(ctx_lines)
        return f"{ctx_str}\n\n[Mensagem do Usuário]: {user_text}"
