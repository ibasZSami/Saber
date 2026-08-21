"""Parses PT-BR reminder phrases into (message, fire_at, recurring_seconds) —
FASE 12. Deliberately simple pattern matching, same philosophy as the other
deterministic keyword commands already in orchestrator.py (nerd mode, vision
toggle) rather than a general NLP/date parser. Returns None when the text
isn't recognizable, so callers fall through to the normal AI path."""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

TRIGGER_WORDS = ("me lembra", "me lembre", "me avisa", "me avise", "lembrete")

_RELATIVE_RE = re.compile(
    r"\bem\s+(\d+)\s*(segundos?|minutos?|horas?)\b", re.IGNORECASE
)
_ABSOLUTE_RE = re.compile(r"\bàs?\s+(\d{1,2})[:h](\d{2})?\b", re.IGNORECASE)
_DAILY_RE = re.compile(r"\btodo\s+dia\b", re.IGNORECASE)

_UNIT_SECONDS = {
    "segundo": 1, "segundos": 1,
    "minuto": 60, "minutos": 60,
    "hora": 3600, "horas": 3600,
}

DEFAULT_MESSAGE = "lembrete"


@dataclass(frozen=True)
class ParsedReminder:
    message: str
    fire_at: float
    recurring_seconds: Optional[float]


def _clean_message(text: str, match: re.Match) -> str:
    """Strips the matched time phrase and any trigger word/leading "de" so
    what remains is just the reminder's content — falls back to a generic
    label when nothing meaningful is left (e.g. "me lembra às 18h" alone)."""
    without_time = (text[:match.start()] + text[match.end():]).strip()
    lower = without_time.lower()
    for trigger in TRIGGER_WORDS:
        idx = lower.find(trigger)
        if idx != -1:
            without_time = without_time[:idx] + without_time[idx + len(trigger):]
            lower = without_time.lower()
    without_time = without_time.strip(" ,.")
    if without_time.lower().startswith("todo dia"):
        without_time = without_time[len("todo dia"):].strip(" ,.")
    if without_time.lower().startswith("de "):
        without_time = without_time[3:].strip()
    return without_time or DEFAULT_MESSAGE


def parse(text: str, now: Optional[float] = None) -> Optional[ParsedReminder]:
    lower = text.lower()
    if not any(trigger in lower for trigger in TRIGGER_WORDS):
        return None
    now = now if now is not None else time.time()

    rel_match = _RELATIVE_RE.search(text)
    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2).lower()
        fire_at = now + amount * _UNIT_SECONDS[unit]
        return ParsedReminder(message=_clean_message(text, rel_match), fire_at=fire_at, recurring_seconds=None)

    abs_match = _ABSOLUTE_RE.search(text)
    if abs_match:
        hour = int(abs_match.group(1))
        minute = int(abs_match.group(2) or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        base = datetime.fromtimestamp(now)
        target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= base:
            target += timedelta(days=1)
        recurring = 86400.0 if _DAILY_RE.search(text) else None
        return ParsedReminder(
            message=_clean_message(text, abs_match), fire_at=target.timestamp(), recurring_seconds=recurring,
        )

    return None
