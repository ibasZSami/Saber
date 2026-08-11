from src.ai.context import ContextManager


class TestContextManager:
    def test_vision_enabled_message(self):
        ctx = ContextManager()
        prompt = ctx.build_prompt_context({}, "oi", vision_enabled=True)
        assert "Ativada" in prompt

    def test_vision_disabled_message_by_default(self):
        ctx = ContextManager()
        prompt = ctx.build_prompt_context({}, "oi")
        assert "Desativada" in prompt

    def test_includes_memories(self):
        ctx = ContextManager()
        prompt = ctx.build_prompt_context({"nome": "Fulano"}, "oi")
        assert "nome: Fulano" in prompt

    def test_no_memories_line_when_empty(self):
        ctx = ContextManager()
        prompt = ctx.build_prompt_context({}, "oi")
        assert "Memórias salvas" not in prompt

    def test_includes_app_context(self):
        ctx = ContextManager()
        ctx.set_app_context({"window_title": "VSCode", "category": "coding"})
        prompt = ctx.build_prompt_context({}, "oi")
        assert "VSCode" in prompt
        assert "coding" in prompt

    def test_ends_with_user_message(self):
        ctx = ContextManager()
        prompt = ctx.build_prompt_context({}, "Qual é a capital da França?")
        assert prompt.strip().endswith("Qual é a capital da França?")
