from src.ai.agent_response import parse_agent_response


class TestParseAgentResponse:
    def test_parses_a_normal_step(self):
        raw = '{"thought": "vou pesquisar", "done": false, "result": null, "action": "search_web", "action_param": "gatos"}'
        parsed = parse_agent_response(raw)
        assert parsed["done"] is False
        assert parsed["action"] == "search_web"
        assert parsed["action_param"] == "gatos"

    def test_parses_a_done_step(self):
        raw = '{"thought": "achei", "done": true, "result": "o preço é R$50", "action": "Nenhuma", "action_param": ""}'
        parsed = parse_agent_response(raw)
        assert parsed["done"] is True
        assert parsed["result"] == "o preço é R$50"

    def test_missing_action_defaults_to_nenhuma(self):
        raw = '{"thought": "x", "done": false, "result": null}'
        parsed = parse_agent_response(raw)
        assert parsed["action"] == "Nenhuma"

    def test_extracts_json_surrounded_by_extra_text(self):
        raw = 'Aqui está: {"done": false, "action": "search_web", "action_param": "x"} pronto'
        parsed = parse_agent_response(raw)
        assert parsed["action"] == "search_web"

    def test_malformed_json_ends_the_task_instead_of_looping(self):
        """Regression guard: unparseable output must never be treated as
        'keep going' — that would loop blind against a model that stopped
        producing valid JSON."""
        raw = "isso não é JSON de jeito nenhum"
        parsed = parse_agent_response(raw)
        assert parsed["done"] is True
        assert parsed["result"]

    def test_object_with_action_param_as_dict(self):
        raw = '{"done": false, "action": "set_app_volume", "action_param": {"application": "discord", "level": 20}}'
        parsed = parse_agent_response(raw)
        assert parsed["action_param"] == {"application": "discord", "level": 20}

    def test_defaults_done_to_false_when_absent(self):
        raw = '{"action": "search_web", "action_param": "x"}'
        parsed = parse_agent_response(raw)
        assert parsed["done"] is False
