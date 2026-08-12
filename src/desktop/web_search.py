import logging
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
FETCH_TIMEOUT_S = 8
DEFAULT_MAX_RESULTS = 5


class WebSearchProvider:
    """Real web search with no API key — scrapes DuckDuckGo's plain HTML
    results page (no JS, meant for lightweight clients), used by
    ResearchManager. Never invents results: any failure (network, parsing, no
    matches) returns an empty list, which callers must treat as "nothing
    found" rather than guessing."""

    def search(self, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> List[Dict[str, str]]:
        if not query or not query.strip():
            return []
        try:
            resp = requests.post(
                DUCKDUCKGO_HTML_URL,
                data={"q": query},
                timeout=FETCH_TIMEOUT_S,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
        except Exception as e:
            logging.warning(f"Web search request failed for {query!r}: {e}")
            return []

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for item in soup.select(".result")[:max_results]:
                title_el = item.select_one(".result__a")
                if title_el is None:
                    continue
                snippet_el = item.select_one(".result__snippet")
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": title_el.get("href", ""),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })
            return results
        except Exception as e:
            logging.warning(f"Failed to parse web search results for {query!r}: {e}")
            return []
