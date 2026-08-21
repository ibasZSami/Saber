from src.memory.relevance import DEFAULT_MAX_MEMORIES, select_relevant_memories


class TestSelectRelevantMemories:
    def test_empty_memories_returns_empty(self):
        assert select_relevant_memories({}, "qual minha cor favorita?") == {}

    def test_empty_user_text_returns_empty(self):
        assert select_relevant_memories({"cor favorita": "azul"}, "") == {}

    def test_key_phrase_mentioned_directly_is_included(self):
        memories = {"cor favorita": "azul"}
        result = select_relevant_memories(memories, "qual é minha cor favorita?")
        assert result == {"cor favorita": "azul"}

    def test_unrelated_message_excludes_the_memory(self):
        memories = {"cor favorita": "azul"}
        result = select_relevant_memories(memories, "que horas são agora?")
        assert result == {}

    def test_token_overlap_with_the_value_is_enough(self):
        memories = {"time do coração": "flamengo"}
        result = select_relevant_memories(memories, "vamos ver o jogo do flamengo hoje?")
        assert "time do coração" in result

    def test_multiple_relevant_memories_ranked_by_score(self):
        memories = {
            "cor favorita": "azul",
            "comida favorita": "pizza",
            "cidade natal": "São Paulo",
        }
        result = select_relevant_memories(memories, "qual minha cor favorita e minha comida favorita?")
        assert set(result.keys()) == {"cor favorita", "comida favorita"}
        assert "cidade natal" not in result

    def test_stopwords_alone_never_count_as_relevance(self):
        memories = {"nota": "isso é para você com"}
        result = select_relevant_memories(memories, "eu com você para isso")
        assert result == {}

    def test_respects_max_count(self):
        memories = {f"fato {i}": "python" for i in range(20)}
        result = select_relevant_memories(memories, "me fala sobre python", max_count=3)
        assert len(result) == 3

    def test_default_max_count_matches_constant(self):
        memories = {f"fato {i}": "python" for i in range(20)}
        result = select_relevant_memories(memories, "me fala sobre python")
        assert len(result) == DEFAULT_MAX_MEMORIES

    def test_case_insensitive_key_match(self):
        memories = {"Cor Favorita": "azul"}
        result = select_relevant_memories(memories, "MINHA COR FAVORITA")
        assert "Cor Favorita" in result

    def test_non_string_value_is_handled(self):
        memories = {"idade": 30}
        result = select_relevant_memories(memories, "qual minha idade")
        assert "idade" in result
