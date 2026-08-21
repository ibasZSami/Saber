"""Relevance filtering for long-term memory — "Memória em camadas" part 1.
Every saved memory used to always enter the prompt on every single message,
regardless of whether it had anything to do with what the user just said —
harmless with 3 memories saved, noisy and token-expensive once there are 50.

Deliberately no embeddings/vector store here — that's a real dependency and
a real design commitment (which store, how to keep it in sync with
remember/forget) that deserves its own pass, not a quick addition. Keyword
overlap between the message and each memory's key/value is enough to catch
"the user is talking about something they told Silva to remember" without
any of that."""

import re
from typing import Dict

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Common short PT-BR words that overlap with almost any memory's value by
# chance (articles, prepositions, pronouns) — excluded so a coincidental
# "de"/"o"/"que" match doesn't count as relevance.
_STOPWORDS = {
    "a", "o", "os", "as", "de", "da", "do", "das", "dos", "que", "e", "é",
    "um", "uma", "uns", "umas", "com", "em", "no", "na", "nos", "nas",
    "pra", "pro", "para", "por", "sem", "sobre", "meu", "minha", "meus",
    "minhas", "seu", "sua", "seus", "suas", "eu", "voce", "você", "silva",
    "ele", "ela", "isso", "essa", "esse", "esta", "este", "tem", "ter",
}

DEFAULT_MAX_MEMORIES = 8


def _tokens(text: str) -> set:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _relevance_score(key: str, value: str, user_text_lower: str) -> float:
    score = 0.0
    # A strong, direct signal: the user's message literally contains the
    # memory's key phrase (e.g. remembered "cor favorita", asked "qual é
    # minha cor favorita?") — weighted well above plain token overlap.
    if key.strip() and key.strip().lower() in user_text_lower:
        score += 3.0
    overlap = _tokens(user_text_lower) & (_tokens(key) | _tokens(value))
    score += len(overlap)
    return score


def select_relevant_memories(memories: Dict[str, str], user_text: str, max_count: int = DEFAULT_MAX_MEMORIES) -> Dict[str, str]:
    """Returns only the memories that actually relate to `user_text`, most
    relevant first, capped at `max_count`. A memory that scores zero
    relevance is left out entirely — better to say nothing than to pad the
    prompt with facts the current message has nothing to do with."""
    if not memories or not user_text:
        return {}
    user_text_lower = user_text.lower()
    scored = sorted(
        (
            (_relevance_score(key, str(value), user_text_lower), key, value)
            for key, value in memories.items()
        ),
        key=lambda t: t[0], reverse=True,
    )
    relevant = [(key, value) for score, key, value in scored if score > 0]
    return dict(relevant[:max_count])
