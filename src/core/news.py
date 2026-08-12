import logging
import time
from typing import Dict, List
from xml.etree import ElementTree

import requests

# Google News' public RSS feeds — no API key needed. Feed order is Google's own
# top-story ranking, so the first item(s) double as a "most prominent story
# right now" signal, good enough as an "important/well-covered" proxy without
# building a real trending-detection system.
BRAZIL_NEWS_FEED_URL = "https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-BR"
WORLD_NEWS_FEED_URL = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"

DEFAULT_CACHE_TTL_S = 45 * 60  # refetch each feed at most every 45 minutes
FETCH_TIMEOUT_S = 6
HEADLINES_PER_FEED = 6


class NewsProvider:
    """Pulls top Brazil/world headlines for spontaneous-talk to draw on, cached
    with a TTL so it doesn't hit the network on every idle-chat check."""

    def __init__(self, cache_ttl_s: float = DEFAULT_CACHE_TTL_S):
        self.cache_ttl_s = cache_ttl_s
        self._cache: Dict[str, List[str]] = {"brasil": [], "mundo": []}
        # None (not 0.0) so the first call always fetches — time.monotonic()'s
        # reference point is unspecified and can itself start near 0 (e.g. right
        # after a Windows boot), which made "0.0 - now" wrongly look like it was
        # still within a fresh TTL window and skip fetching entirely.
        self._last_fetch_time = None

    def _fetch_feed(self, url: str) -> List[str]:
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT_S, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            titles = []
            for item in root.findall(".//item")[:HEADLINES_PER_FEED]:
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    titles.append(title_el.text.strip())
            return titles
        except Exception as e:
            logging.warning(f"Failed to fetch news feed {url}: {e}")
            return []

    def get_headlines(self, force_refresh: bool = False) -> Dict[str, List[str]]:
        """Returns {"brasil": [...], "mundo": [...]}, refetching whichever feeds
        are stale. A fetch failure keeps the previous cached headlines instead of
        wiping them out with an empty list, so a transient network hiccup doesn't
        silence spontaneous talk's news topic for a full TTL window."""
        now = time.monotonic()
        is_stale = self._last_fetch_time is None or (now - self._last_fetch_time) >= self.cache_ttl_s
        if force_refresh or is_stale:
            brasil = self._fetch_feed(BRAZIL_NEWS_FEED_URL)
            mundo = self._fetch_feed(WORLD_NEWS_FEED_URL)
            if brasil:
                self._cache["brasil"] = brasil
            if mundo:
                self._cache["mundo"] = mundo
            self._last_fetch_time = now
        return {"brasil": list(self._cache["brasil"]), "mundo": list(self._cache["mundo"])}
