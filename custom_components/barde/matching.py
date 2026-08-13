"""Fuzzy name matching for rooms, players and media titles.

Pure Python on purpose — no Home Assistant imports — so the matching rules can
be tested without a running hass instance.

Spoken room names rarely match entity names literally: the satellite in the
living room is called "Wohnzimmerlautsprecher", the user says "Wohnzimmer".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
import re

_UMLAUTS = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "à": "a",
        "á": "a",
        "â": "a",
        "è": "e",
        "é": "e",
        "ê": "e",
        "ï": "i",
        "î": "i",
        "ô": "o",
        "ó": "o",
        "ù": "u",
        "û": "u",
        "ç": "c",
        "ñ": "n",
    }
)

_NON_WORD = re.compile(r"[^a-z0-9]+")

# Words that describe the device, not the room. Dropped before comparing so
# "Küche Lautsprecher" and "Küche" collapse onto the same core form.
_FILLER_WORDS = frozenset(
    {
        "lautsprecher",
        "speaker",
        "boxen",
        "box",
        "player",
        "media",
        "mediaplayer",
        "musik",
        "music",
        "assistant",
        "sonos",
        "echo",
        "dot",
        "homepod",
        "chromecast",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "im",
        "in",
        "ins",
        "am",
        "auf",
        "zum",
        "zur",
        # "&" normalizes to nothing, so dropping the spoken "und" makes
        # "Kack- und Sachgeschichten" and "Kack & Sachgeschichten" identical.
        "und",
        "and",
    }
)

# Words that describe the *request*, not the title. "Spiel Hazbin Hotel Songs"
# has to become a search for "Hazbin Hotel" when the literal phrase finds
# nothing.
_QUERY_FILLER = frozenset(
    {
        "songs",
        "song",
        "lieder",
        "lied",
        "titel",
        "tracks",
        "musik",
        "music",
        "etwas",
        "was",
        "irgendwas",
        "von",
    }
)

# Below this the match is treated as "no match" rather than a bad guess.
MATCH_THRESHOLD = 0.6


def normalize(text: str) -> str:
    """Lowercase, unfold umlauts, drop punctuation, collapse whitespace."""
    lowered = text.casefold().translate(_UMLAUTS)
    return _NON_WORD.sub(" ", lowered).strip()


def tokenize(text: str) -> list[str]:
    """Split into normalized words."""
    normalized = normalize(text)
    return normalized.split() if normalized else []


def core_form(text: str) -> str:
    """Return the normalized text without device/filler words.

    Falls back to the plain normalized form when everything would be dropped
    (a player literally named "Lautsprecher" stays matchable).
    """
    words = [word for word in tokenize(text) if word not in _FILLER_WORDS]
    return " ".join(words) if words else normalize(text)


def ampersand_variant(text: str) -> str:
    """Spell the German "und" back as "&" for provider search.

    Speech-to-text writes what was said: "Kack- und Sachgeschichten". The
    library writes the title: "Kack & Sachgeschichten". Returns an empty string
    when there is nothing to swap.
    """
    variant = re.sub(r"-\s+und\s+", " und ", text, flags=re.IGNORECASE)
    variant = re.sub(r"\s+und\s+", " & ", variant, flags=re.IGNORECASE)
    return variant if variant != text else ""


def strip_query_filler(text: str) -> str:
    """Drop generic request words from a search query.

    Keeps the original spelling of what is left; returns an empty string when
    nothing would remain.
    """
    words = [word for word in text.split() if normalize(word) not in _QUERY_FILLER]
    return " ".join(words).strip()


def match_score(query: str, candidate: str) -> float:
    """Return how well ``query`` matches ``candidate`` on a 0..1 scale."""
    if not query or not candidate:
        return 0.0
    return max(
        _score_pair(normalize(query), normalize(candidate)),
        _score_pair(core_form(query), core_form(candidate)),
    )


def _score_pair(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    # "wohnzimmer" vs "wohnzimmerlautsprecher"
    if candidate.startswith(query) or query.startswith(candidate):
        return 0.92
    if query in candidate or candidate in query:
        return 0.82

    query_words = set(query.split())
    candidate_words = set(candidate.split())
    shared = query_words & candidate_words
    if shared:
        coverage = len(shared) / max(len(query_words), len(candidate_words))
        return 0.6 + 0.2 * coverage

    ratio = SequenceMatcher(None, query, candidate).ratio()
    # Typos and STT wobble ("wohnzimma") — only trust a high ratio.
    return ratio * 0.75 if ratio >= 0.8 else 0.0


def best_match[T](
    query: str,
    candidates: Mapping[T, Iterable[str]],
    threshold: float = MATCH_THRESHOLD,
) -> tuple[T, float] | None:
    """Pick the key whose aliases match ``query`` best.

    ``candidates`` maps an opaque key (entity id, playlist name, …) to every
    name that key may be called by. Ties are broken by the first key in
    iteration order, so callers control the fallback by sorting beforehand.
    """
    best: tuple[T, float] | None = None
    for key, aliases in candidates.items():
        score = max((match_score(query, alias) for alias in aliases), default=0.0)
        if score >= threshold and (best is None or score > best[1]):
            best = (key, score)
    return best
