from src.ai.tools import parse_ai_response


class TestParseAIResponse:
    def test_parses_clean_json(self):
        raw = '{"speech": "oi", "animation": "HAPPY", "action": "Nenhuma"}'
        result = parse_ai_response(raw)
        assert result["speech"] == "oi"
        assert result["animation"] == "HAPPY"

    def test_null_speech_does_not_become_the_word_none(self):
        raw = '{"speech": null, "animation": "IDLE", "action": "Nenhuma", "action_param": ""}'
        result = parse_ai_response(raw)
        assert result["speech"] == ""

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

    def test_strips_narration_asterisks_from_valid_json(self):
        raw = '{"speech": "*sorri* Oi! *acena*", "animation": "HAPPY"}'
        result = parse_ai_response(raw)
        assert result["speech"] == "Oi!"

    def test_strips_narration_in_parens_and_brackets(self):
        raw = '{"speech": "(ri) Oi! [pensativo] tudo bem?", "animation": "HAPPY"}'
        result = parse_ai_response(raw)
        assert result["speech"] == "Oi! tudo bem?"

    def test_does_not_silence_a_reply_entirely_wrapped_in_parens(self):
        # A real answer that happens to be entirely inside parens must still be
        # spoken — stripping it down to nothing would silently drop a real reply.
        raw = '{"speech": "(Sim, são 5 horas agora)", "animation": "TALKING"}'
        result = parse_ai_response(raw)
        assert result["speech"] == "(Sim, são 5 horas agora)"

    def test_salvages_speech_field_from_broken_json_instead_of_raw_dump(self):
        # Missing closing brace for the outer object — json.loads fails,
        # but the speech field itself is intact and should be recovered
        # cleanly instead of speaking the literal '{"speech": ...' aloud.
        raw = '{"speech": "Oi, tudo bem?", "animation": "HAPPY"'
        result = parse_ai_response(raw)
        assert result["speech"] == "Oi, tudo bem?"
        assert "{" not in result["speech"]

    def test_stays_quiet_when_json_too_broken_to_salvage(self):
        raw = '{"animation": "HAPPY", "action": "Nenhuma"'
        result = parse_ai_response(raw)
        assert result["speech"] == ""
        assert result["animation"] == "CONFUSED"
