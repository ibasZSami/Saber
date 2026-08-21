"""Attention Budget — smarter spontaneous-talk pacing than a fixed timer.
Previously: "at least N seconds since the last spontaneous remark", same N
regardless of what the user is actually doing. This tracks a regenerating
budget instead — a token bucket, not a clock — so pacing adapts to context:
slower regen while the user is gaming (don't interrupt), faster while idle
(nothing else competing for attention), normal otherwise. One point is
spent per remark; a comment only happens once enough has regenerated. The
cap keeps a long silent stretch from banking up into a burst of comments
the moment it ends."""

import time
from typing import Optional

# Points per second regenerated in each context — the "normal"/"nerd" base
# rates are chosen so the *average* cadence roughly matches the old fixed
# intervals (1 point / 75s normal, 1 point / 40s nerd) while actually
# varying with context instead of being flat.
REGEN_RATE_NORMAL = 1.0 / 75.0
REGEN_RATE_NERD = 1.0 / 40.0
REGEN_RATE_GAMING_MULTIPLIER = 0.4  # slower — don't interrupt gameplay
REGEN_RATE_IDLE_MULTIPLIER = 1.6    # faster — nothing else competing for attention

MAX_BUDGET = 1.5
SPEND_PER_COMMENT = 1.0


class AttentionBudget:
    def __init__(self, now: Optional[float] = None):
        self._budget = 0.0
        self._last_update = now if now is not None else time.monotonic()

    def _regen_rate(self, nerd_mode: bool, is_game: bool, is_idle: bool) -> float:
        base = REGEN_RATE_NERD if nerd_mode else REGEN_RATE_NORMAL
        if is_game:
            return base * REGEN_RATE_GAMING_MULTIPLIER
        if is_idle:
            return base * REGEN_RATE_IDLE_MULTIPLIER
        return base

    def _update(self, nerd_mode: bool, is_game: bool, is_idle: bool, now: float):
        elapsed = max(0.0, now - self._last_update)
        rate = self._regen_rate(nerd_mode, is_game, is_idle)
        self._budget = min(MAX_BUDGET, self._budget + elapsed * rate)
        self._last_update = now

    def can_speak(
        self, nerd_mode: bool = False, is_game: bool = False, is_idle: bool = False,
        now: Optional[float] = None,
    ) -> bool:
        """Regenerates the budget up to `now` given the current context,
        then reports whether there's enough to afford one remark. Does NOT
        spend it — call spend() separately once the remark actually
        happens, so a caller that decides not to speak after all (e.g. the
        AI had nothing to say) doesn't lose the budget for nothing."""
        now = now if now is not None else time.monotonic()
        self._update(nerd_mode, is_game, is_idle, now)
        return self._budget >= SPEND_PER_COMMENT

    def spend(self, now: Optional[float] = None):
        self._budget = max(0.0, self._budget - SPEND_PER_COMMENT)
        if now is not None:
            self._last_update = now

    def reset(self, now: Optional[float] = None):
        self._budget = 0.0
        self._last_update = now if now is not None else time.monotonic()
