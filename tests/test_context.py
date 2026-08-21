import time

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


class TestStructuredScreenContext:
    def test_no_screen_context_line_without_a_timestamp(self):
        """No vision mode active (or orchestrator never called
        set_screen_context) — must not fabricate a screen context line."""
        ctx = ContextManager()
        prompt = ctx.build_prompt_context({}, "oi")
        assert "Contexto de tela" not in prompt

    def test_fresh_reading_shows_window_and_category(self):
        ctx = ContextManager()
        ctx.set_screen_context({
            "window_title": "Elden Ring", "category": "gaming", "changed": False, "timestamp": time.time(),
        })
        prompt = ctx.build_prompt_context({}, "oi")
        assert "Elden Ring" in prompt
        assert "gaming" in prompt
        assert "Contexto de tela" in prompt

    def test_recently_changed_reading_is_flagged(self):
        ctx = ContextManager()
        ctx.set_screen_context({
            "window_title": "Chrome", "category": "browser", "changed": True, "timestamp": time.time(),
        })
        prompt = ctx.build_prompt_context({}, "oi")
        assert "mudou recentemente" in prompt

    def test_stale_reading_is_never_presented_as_current(self):
        """The core FASE 10/11 safety requirement: an old reading must not
        be described as if it reflects the screen right now."""
        ctx = ContextManager()
        ctx.set_screen_context({
            "window_title": "Notepad", "category": "general", "changed": False,
            "timestamp": time.time() - 999,
        })
        prompt = ctx.build_prompt_context({}, "oi")
        assert "Notepad" not in prompt
        assert "nenhuma leitura recente disponível" in prompt
