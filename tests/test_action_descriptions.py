from src.core.action_descriptions import describe_action


class TestDescribeAction:
    def test_open_application(self):
        assert describe_action("open_application", "chrome") == 'Silva quer abrir o aplicativo "chrome".'

    def test_close_application(self):
        assert describe_action("close_application", "discord") == 'Silva quer fechar o aplicativo "discord".'

    def test_open_url(self):
        text = describe_action("open_url", "https://example.com")
        assert "https://example.com" in text
        assert "abrir" in text.lower()

    def test_set_app_volume_with_dict_param(self):
        text = describe_action("set_app_volume", {"application": "spotify", "level": 40})
        assert "spotify" in text
        assert "40" in text

    def test_set_app_volume_with_malformed_param_still_returns_text(self):
        text = describe_action("set_app_volume", "not_a_dict")
        assert text  # never blank, even for a shape it doesn't recognize

    def test_unknown_action_falls_back_to_generic_text(self):
        text = describe_action("fly_to_moon", "now")
        assert "fly_to_moon" in text
        assert text  # never blank — the dialog always has something to show
