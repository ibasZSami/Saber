"""Continuous Vision — FASE 10. Explicit modes instead of a single on/off
toggle, plus a small in-memory ring buffer with TTL so anything built from
recent screen context can tell fresh from stale — never presents an expired
reading as if it were current (see src/ai/context.py's FASE 11 use of this).

Backward compatibility: the two existing settings (screen_monitoring_enabled,
private_mode) keep driving OFF/ACTIVE exactly as before for every existing
install — see CompanionOrchestrator._compute_vision_mode(). CONTEXT/AWARENESS
are new capabilities, reachable only through the new optional
`screen_vision_mode` setting override; nothing existing changes behavior
unless that setting is explicitly set."""

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum


class VisionMode(str, Enum):
    OFF = "OFF"            # never captures — matches today's default/private-mode behavior
    CONTEXT = "CONTEXT"    # periodic pixel-diff tracking only, no image ever sent to the AI
    AWARENESS = "AWARENESS"  # CONTEXT + a short rolling buffer feeds structured text context into every prompt
    ACTIVE = "ACTIVE"      # CONTEXT + a live screenshot is attached on demand — today's "monitoring, not private" behavior


DEFAULT_TTL_SECONDS = 30.0
DEFAULT_MAX_ENTRIES = 5


@dataclass(frozen=True)
class VisionSnapshot:
    timestamp: float
    window_title: str
    category: str
    changed: bool


class ContinuousVisionBuffer:
    """Ring buffer of recent screen-context snapshots — metadata only, never
    raw pixels, so AWARENESS mode's "what was on screen and when" doesn't
    mean holding screenshots in memory. Anything older than ttl_seconds is
    treated as expired and excluded from freshest()/recent()."""

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS, max_entries: int = DEFAULT_MAX_ENTRIES):
        self.ttl_seconds = ttl_seconds
        self._entries = deque(maxlen=max_entries)

    def add(self, window_title: str, category: str, changed: bool):
        self._entries.append(VisionSnapshot(time.time(), window_title, category, changed))

    def freshest(self):
        """Most recent snapshot, or None if the buffer is empty or its
        newest entry has already expired — callers must never treat an
        expired entry as current."""
        if not self._entries:
            return None
        newest = self._entries[-1]
        if time.time() - newest.timestamp > self.ttl_seconds:
            return None
        return newest

    def recent(self):
        """All non-expired entries, oldest first."""
        now = time.time()
        return [e for e in self._entries if now - e.timestamp <= self.ttl_seconds]

    def clear(self):
        self._entries.clear()
