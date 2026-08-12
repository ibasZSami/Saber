from unittest.mock import MagicMock, patch

from src.desktop.web_search import WebSearchProvider

_SAMPLE_HTML = """
<html><body>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="https://example.com/a">Resultado A</a>
  <a class="result__snippet">Trecho do resultado A</a>
</div>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="https://example.com/b">Resultado B</a>
  <a class="result__snippet">Trecho do resultado B</a>
</div>
</body></html>
"""


def _fake_response(text=_SAMPLE_HTML, status=200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


class TestWebSearchProvider:
    @patch("src.desktop.web_search.requests.post")
    def test_parses_title_url_and_snippet(self, mock_post):
        mock_post.return_value = _fake_response()
        provider = WebSearchProvider()

        results = provider.search("python asyncio")

        assert len(results) == 2
        assert results[0] == {
            "title": "Resultado A",
            "url": "https://example.com/a",
            "snippet": "Trecho do resultado A",
        }
        assert results[1]["title"] == "Resultado B"

    @patch("src.desktop.web_search.requests.post")
    def test_respects_max_results(self, mock_post):
        mock_post.return_value = _fake_response()
        provider = WebSearchProvider()

        results = provider.search("python asyncio", max_results=1)

        assert len(results) == 1

    @patch("src.desktop.web_search.requests.post")
    def test_network_failure_returns_empty_list(self, mock_post):
        mock_post.side_effect = Exception("network down")
        provider = WebSearchProvider()

        assert provider.search("qualquer coisa") == []

    @patch("src.desktop.web_search.requests.post")
    def test_http_error_returns_empty_list(self, mock_post):
        mock_post.return_value = _fake_response(status=503)
        provider = WebSearchProvider()

        assert provider.search("qualquer coisa") == []

    @patch("src.desktop.web_search.requests.post")
    def test_no_results_returns_empty_list(self, mock_post):
        mock_post.return_value = _fake_response(text="<html><body>sem resultados</body></html>")
        provider = WebSearchProvider()

        assert provider.search("query obscura sem resultado nenhum") == []

    def test_empty_query_returns_empty_list_without_network_call(self):
        provider = WebSearchProvider()
        with patch("src.desktop.web_search.requests.post") as mock_post:
            assert provider.search("") == []
            assert provider.search("   ") == []
            mock_post.assert_not_called()

    @patch("src.desktop.web_search.requests.post")
    def test_result_missing_snippet_still_returns_title_and_url(self, mock_post):
        html = """
        <div class="result">
          <a class="result__a" href="https://example.com/c">Só título</a>
        </div>
        """
        mock_post.return_value = _fake_response(text=html)
        provider = WebSearchProvider()

        results = provider.search("algo")

        assert results == [{"title": "Só título", "url": "https://example.com/c", "snippet": ""}]
