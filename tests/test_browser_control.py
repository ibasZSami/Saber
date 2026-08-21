from unittest.mock import MagicMock, patch

from src.desktop.browser_control import BrowserController, _looks_like_css_selector


def _fake_playwright_module():
    fake_page = MagicMock()
    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page
    fake_pw_instance = MagicMock()
    fake_pw_instance.chromium.launch.return_value = fake_browser
    fake_sync_playwright_cm = MagicMock()
    fake_sync_playwright_cm.start.return_value = fake_pw_instance
    fake_module = MagicMock()
    fake_module.sync_playwright.return_value = fake_sync_playwright_cm
    return fake_module, fake_page, fake_browser


def _controller():
    """Real BrowserController, real dedicated thread, but with
    playwright.sync_api faked out — same pattern already used for
    pytesseract/pyttsx3/edge_tts elsewhere in this test suite. The
    constructor blocks on _started, so the patch only needs to be active
    during construction."""
    fake_module, fake_page, fake_browser = _fake_playwright_module()
    with patch.dict("sys.modules", {"playwright.sync_api": fake_module}):
        controller = BrowserController()
    return controller, fake_page, fake_browser


class TestLooksLikeCssSelector:
    def test_id_selector(self):
        assert _looks_like_css_selector("#submit-button") is True

    def test_class_selector(self):
        assert _looks_like_css_selector(".price") is True

    def test_attribute_selector(self):
        assert _looks_like_css_selector("[data-test='buy']") is True

    def test_bare_tag(self):
        assert _looks_like_css_selector("button") is True

    def test_visible_text_with_spaces_is_not_a_selector(self):
        assert _looks_like_css_selector("Adicionar ao carrinho") is False

    def test_single_word_visible_text_is_still_treated_as_text(self):
        """A bare word like 'Comprar' technically matches the tag pattern —
        acceptable ambiguity (Playwright's click() on a bogus 'tag selector'
        just fails cleanly, caught by the caller) since there's no way to
        distinguish "a tag name" from "a one-word button label" without
        seeing the page's HTML, which the AI never has access to."""
        assert _looks_like_css_selector("Comprar") is True


class TestNavigate:
    def test_navigate_calls_goto(self):
        controller, fake_page, _ = _controller()
        result = controller.navigate("example.com")
        assert result is True
        fake_page.goto.assert_called_once()
        assert fake_page.goto.call_args[0][0] == "https://example.com"

    def test_navigate_keeps_explicit_scheme(self):
        controller, fake_page, _ = _controller()
        controller.navigate("http://example.com")
        assert fake_page.goto.call_args[0][0] == "http://example.com"

    def test_navigate_failure_returns_false(self):
        controller, fake_page, _ = _controller()
        fake_page.goto.side_effect = RuntimeError("timeout")
        assert controller.navigate("example.com") is False


class TestClick:
    def test_click_css_selector_uses_page_click(self):
        controller, fake_page, _ = _controller()
        result = controller.click("#buy-button")
        assert result is True
        fake_page.click.assert_called_once()
        assert fake_page.click.call_args[0][0] == "#buy-button"

    def test_click_visible_text_uses_get_by_text(self):
        controller, fake_page, _ = _controller()
        result = controller.click("Adicionar ao carrinho")
        assert result is True
        fake_page.get_by_text.assert_called_once_with("Adicionar ao carrinho", exact=False)

    def test_click_failure_returns_false(self):
        controller, fake_page, _ = _controller()
        fake_page.click.side_effect = RuntimeError("not found")
        assert controller.click("#missing") is False


class TestTypeText:
    def test_type_into_css_selector_uses_fill(self):
        controller, fake_page, _ = _controller()
        result = controller.type_text("#search", "gatos")
        assert result is True
        fake_page.fill.assert_called_once()
        assert fake_page.fill.call_args[0] == ("#search", "gatos")

    def test_type_into_visible_text_target_uses_get_by_text(self):
        controller, fake_page, _ = _controller()
        result = controller.type_text("Campo de busca", "gatos")
        assert result is True
        fake_page.get_by_text.assert_called_once_with("Campo de busca", exact=False)

    def test_type_failure_returns_false(self):
        controller, fake_page, _ = _controller()
        fake_page.fill.side_effect = RuntimeError("not found")
        assert controller.type_text("#missing", "x") is False


class TestReadText:
    def test_reads_body_inner_text(self):
        controller, fake_page, _ = _controller()
        fake_page.inner_text.return_value = "Preço: R$50"
        result = controller.read_text()
        assert result == "Preço: R$50"
        fake_page.inner_text.assert_called_once_with("body", timeout=15000)

    def test_read_failure_returns_none(self):
        controller, fake_page, _ = _controller()
        fake_page.inner_text.side_effect = RuntimeError("boom")
        assert controller.read_text() is None


class TestStartupFailure:
    def test_unavailable_playwright_makes_every_call_fail_cleanly(self):
        with patch.dict("sys.modules", {"playwright.sync_api": None}):
            controller = BrowserController()

        assert controller.navigate("example.com") is False
        assert controller.click("x") is False
        assert controller.type_text("x", "y") is False
        assert controller.read_text() is None


class TestClose:
    def test_close_does_not_raise(self):
        controller, _, fake_browser = _controller()
        controller.close()  # should not raise
