from unittest.mock import MagicMock, patch

from src.core.news import NewsProvider

_SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Principais noticias</title>
<item><title>Manchete um - Fonte</title></item>
<item><title>Manchete dois - Fonte</title></item>
<item><title>Manchete tres - Fonte</title></item>
</channel></rss>"""


def _fake_response(content=_SAMPLE_RSS, status=200):
    resp = MagicMock()
    resp.content = content
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


class TestNewsProvider:
    @patch("src.core.news.time.monotonic", return_value=1.0)
    @patch("src.core.news.requests.get")
    def test_first_call_always_fetches_even_when_monotonic_clock_starts_low(self, mock_get, mock_monotonic):
        """Regression: time.monotonic()'s reference point is unspecified and can
        itself start near 0 (e.g. right after a Windows boot) — initializing the
        "last fetch" sentinel to 0.0 made a fresh provider look like it was still
        within a 45-minute-old TTL window and skip fetching on its very first
        call, so spontaneous talk could go the entire cache TTL with zero news."""
        mock_get.return_value = _fake_response()
        provider = NewsProvider()

        headlines = provider.get_headlines()

        assert headlines["brasil"] == ["Manchete um - Fonte", "Manchete dois - Fonte", "Manchete tres - Fonte"]
        assert mock_get.call_count == 2

    @patch("src.core.news.requests.get")
    def test_fetches_and_parses_titles_from_both_feeds(self, mock_get):
        mock_get.return_value = _fake_response()
        provider = NewsProvider()

        headlines = provider.get_headlines()

        assert headlines["brasil"] == ["Manchete um - Fonte", "Manchete dois - Fonte", "Manchete tres - Fonte"]
        assert headlines["mundo"] == ["Manchete um - Fonte", "Manchete dois - Fonte", "Manchete tres - Fonte"]
        assert mock_get.call_count == 2

    @patch("src.core.news.requests.get")
    def test_does_not_refetch_within_ttl(self, mock_get):
        mock_get.return_value = _fake_response()
        provider = NewsProvider(cache_ttl_s=9999)

        provider.get_headlines()
        provider.get_headlines()

        assert mock_get.call_count == 2  # one per feed, only on the first call

    @patch("src.core.news.requests.get")
    def test_force_refresh_bypasses_ttl(self, mock_get):
        mock_get.return_value = _fake_response()
        provider = NewsProvider(cache_ttl_s=9999)

        provider.get_headlines()
        provider.get_headlines(force_refresh=True)

        assert mock_get.call_count == 4

    @patch("src.core.news.requests.get", side_effect=Exception("network down"))
    def test_network_failure_returns_empty_without_raising(self, mock_get):
        provider = NewsProvider()

        headlines = provider.get_headlines()

        assert headlines == {"brasil": [], "mundo": []}

    @patch("src.core.news.requests.get")
    def test_failed_refresh_keeps_previous_cached_headlines(self, mock_get):
        provider = NewsProvider(cache_ttl_s=0)
        mock_get.return_value = _fake_response()
        first = provider.get_headlines()
        assert first["brasil"]

        mock_get.side_effect = Exception("network down")
        second = provider.get_headlines(force_refresh=True)

        assert second["brasil"] == first["brasil"]

    @patch("src.core.news.requests.get")
    def test_malformed_xml_returns_empty_without_raising(self, mock_get):
        mock_get.return_value = _fake_response(content=b"not xml at all")
        provider = NewsProvider()

        headlines = provider.get_headlines()

        assert headlines == {"brasil": [], "mundo": []}
