"""Real browser automation via Playwright (Chromium) — clicking/reading/
typing inside an actual page, not just opening a URL (see open_url/
search_web in tool_registry.py for that). Highest-risk tool category
alongside mouse/keyboard/terminal — gated the same way (CONFIRM tier, no
dispatch registered at all unless the Settings master switch is on).

Playwright's sync API is thread-affine: the browser/context/page must be
driven from the SAME thread that created them, but this project's tools are
dispatched from whatever worker thread happens to be running at the time
(handle_user_message's worker, the Agent Engine's task loop, ...). So
BrowserController owns one dedicated background thread and a command
queue — every operation is handed to that thread and the caller blocks for
the result, instead of ever touching a Playwright object from an arbitrary
thread.

The AI only ever sees rendered text (read_text), never raw HTML — it has
no way to know a real CSS selector for anything. click()/type_text() take
a `target` that's tried as a CSS selector only if it looks like one
(starts with #, ., or a tag-like word[attr] pattern); otherwise it's
treated as visible text to find and act on (Playwright's get_by_text),
which is what an AI working from rendered text can actually provide."""

import logging
import queue
import re
import threading
from typing import Any, Callable, Optional

DEFAULT_TIMEOUT_MS = 15000
QUEUE_WAIT_TIMEOUT_S = 30
START_TIMEOUT_S = 20

_CSS_SELECTOR_RE = re.compile(r"^[#.\[]|^[a-zA-Z][\w-]*(\[[^\]]+\])?$")


def _looks_like_css_selector(target: str) -> bool:
    return bool(_CSS_SELECTOR_RE.match(target.strip())) and len(target.strip().split()) == 1


class BrowserController:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self._command_queue: "queue.Queue" = queue.Queue()
        self._playwright = None
        self._browser = None
        self._page = None
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started.wait(timeout=START_TIMEOUT_S)

    def _run(self):
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._page = self._browser.new_page()
        except Exception as e:
            logging.error(f"BrowserController failed to start: {e}")
            self._playwright = None
        finally:
            self._started.set()

        while True:
            item = self._command_queue.get()
            if item is None:
                break
            fn, result_holder, done_event = item
            try:
                result_holder["value"] = fn()
            except Exception as e:
                result_holder["error"] = str(e)
            done_event.set()

        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logging.error(f"BrowserController shutdown error: {e}")

    def _call(self, fn: Callable[[], Any]) -> Any:
        if self._playwright is None:
            raise RuntimeError("Navegador não iniciou (Playwright/Chromium indisponível).")
        result_holder: dict = {}
        done_event = threading.Event()
        self._command_queue.put((fn, result_holder, done_event))
        if not done_event.wait(timeout=QUEUE_WAIT_TIMEOUT_S):
            raise RuntimeError("Comando do navegador excedeu o tempo limite.")
        if "error" in result_holder:
            raise RuntimeError(result_holder["error"])
        return result_holder.get("value")

    def navigate(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            self._call(lambda: self._page.goto(url, timeout=DEFAULT_TIMEOUT_MS))
            return True
        except Exception as e:
            logging.error(f"Browser navigate to {url!r} failed: {e}")
            return False

    def click(self, target: str) -> bool:
        try:
            if _looks_like_css_selector(target):
                self._call(lambda: self._page.click(target, timeout=DEFAULT_TIMEOUT_MS))
            else:
                self._call(lambda: self._page.get_by_text(target, exact=False).first.click(timeout=DEFAULT_TIMEOUT_MS))
            return True
        except Exception as e:
            logging.error(f"Browser click on {target!r} failed: {e}")
            return False

    def type_text(self, target: str, text: str) -> bool:
        try:
            if _looks_like_css_selector(target):
                self._call(lambda: self._page.fill(target, text, timeout=DEFAULT_TIMEOUT_MS))
            else:
                self._call(
                    lambda: self._page.get_by_text(target, exact=False).first.fill(text, timeout=DEFAULT_TIMEOUT_MS)
                )
            return True
        except Exception as e:
            logging.error(f"Browser type into {target!r} failed: {e}")
            return False

    def read_text(self) -> Optional[str]:
        try:
            return self._call(lambda: self._page.inner_text("body", timeout=DEFAULT_TIMEOUT_MS))
        except Exception as e:
            logging.error(f"Browser read_text failed: {e}")
            return None

    def close(self):
        self._command_queue.put(None)
