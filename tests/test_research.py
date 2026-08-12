from unittest.mock import MagicMock

from src.core.research import ResearchManager, NO_RESULTS_MESSAGE


def _manager(search_results, chat_return="Resumo gerado."):
    web_search = MagicMock()
    web_search.search.return_value = search_results
    ai_provider = MagicMock()
    ai_provider.chat.return_value = chat_return
    return ResearchManager(web_search, ai_provider), web_search, ai_provider


class TestResearchManager:
    def test_no_results_returns_clear_message_without_calling_ai(self):
        manager, web_search, ai_provider = _manager(search_results=[])

        result = manager.research("query obscura")

        assert result == NO_RESULTS_MESSAGE.format(query="query obscura")
        ai_provider.chat.assert_not_called()

    def test_summarizes_real_results(self):
        results = [
            {"title": "Título A", "url": "https://a.com", "snippet": "Trecho A"},
            {"title": "Título B", "url": "https://b.com", "snippet": "Trecho B"},
        ]
        manager, web_search, ai_provider = _manager(results, chat_return="Resumo: A e B dizem X.")

        summary = manager.research("meu tópico")

        assert summary == "Resumo: A e B dizem X."
        web_search.search.assert_called_once_with("meu tópico")

    def test_prompt_grounds_the_model_in_real_snippets(self):
        results = [{"title": "Título A", "url": "https://a.com", "snippet": "Trecho A real"}]
        manager, web_search, ai_provider = _manager(results)

        manager.research("meu tópico")

        sent_prompt = ai_provider.chat.call_args[0][0]
        sent_system_prompt = ai_provider.chat.call_args[0][1]
        assert "Título A" in sent_prompt
        assert "Trecho A real" in sent_prompt
        assert "meu tópico" in sent_prompt
        assert "nunca invente" in sent_system_prompt.lower()

    def test_strips_whitespace_from_ai_response(self):
        manager, _, _ = _manager(
            [{"title": "T", "url": "u", "snippet": "s"}],
            chat_return="  resposta com espaços  \n",
        )

        assert manager.research("x") == "resposta com espaços"

    def test_skips_results_with_no_title_or_snippet(self):
        results = [{"title": "", "url": "https://a.com", "snippet": ""}, {"title": "Real", "url": "u", "snippet": ""}]
        manager, _, ai_provider = _manager(results)

        manager.research("x")

        sent_prompt = ai_provider.chat.call_args[0][0]
        assert "Real" in sent_prompt
