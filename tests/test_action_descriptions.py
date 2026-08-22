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

    def test_mouse_click(self):
        text = describe_action("mouse_click", {"x": 100, "y": 200})
        assert "100" in text and "200" in text

    def test_mouse_move(self):
        text = describe_action("mouse_move", {"x": 5, "y": 6})
        assert "5" in text and "6" in text

    def test_type_text(self):
        text = describe_action("type_text", {"text": "olá mundo"})
        assert "olá mundo" in text

    def test_press_key(self):
        text = describe_action("press_key", {"key": "enter"})
        assert "enter" in text

    def test_run_terminal_tool_with_args(self):
        text = describe_action("run_terminal_tool", {"name": "nmap", "args": "-sV localhost"})
        assert "nmap" in text
        assert "-sV localhost" in text

    def test_run_terminal_tool_without_args(self):
        text = describe_action("run_terminal_tool", {"name": "nmap"})
        assert "nmap" in text

    def test_browser_navigate(self):
        text = describe_action("browser_navigate", {"url": "example.com"})
        assert "example.com" in text

    def test_browser_click(self):
        text = describe_action("browser_click", {"target": "Comprar agora"})
        assert "Comprar agora" in text

    def test_browser_type(self):
        text = describe_action("browser_type", {"target": "#search", "text": "gatos"})
        assert "#search" in text
        assert "gatos" in text

    def test_index_folder(self):
        text = describe_action("index_folder", {"path": r"C:\Users\usuario\Documentos"})
        assert r"C:\Users\usuario\Documentos" in text

    def test_unknown_action_falls_back_to_generic_text(self):
        text = describe_action("fly_to_moon", "now")
        assert "fly_to_moon" in text
        assert text  # never blank — the dialog always has something to show
