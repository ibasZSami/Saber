from src.ai.tools import parse_ai_response


class TestParseAIResponse:
    def test_parses_clean_json(self):
        raw = '{"speech": "oi", "animation": "HAPPY", "action": "Nenhuma"}'
        result = parse_ai_response(raw)
        assert result["speech"] == "oi"
        assert result["animation"] == "HAPPY"

    def test_extracts_json_surrounded_by_extra_text(self):
        raw = 'Aqui está: {"speech": "oi", "animation": "IDLE"} obrigado!'
        result = parse_ai_response(raw)
        assert result["speech"] == "oi"

    def test_falls_back_to_plain_text_on_non_json(self):
        raw = "isso não é JSON"
        result = parse_ai_response(raw)
        assert result["speech"] == "isso não é JSON"
        assert result["animation"] == "TALKING"
        assert result["action"] == "Nenhuma"

    def test_falls_back_when_json_malformed(self):
        raw = '{"speech": "oi", "animation": }'
        result = parse_ai_response(raw)
        assert result["animation"] == "TALKING"

    def test_handles_nested_object_in_action_param(self):
        raw = '{"speech": "ok", "action": "remember", "action_param": {"key": "cor", "value": "azul"}}'
        result = parse_ai_response(raw)
        assert result["action_param"] == {"key": "cor", "value": "azul"}
