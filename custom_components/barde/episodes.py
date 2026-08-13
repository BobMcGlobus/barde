"""Podcast episodes — picking the right one out of a feed.

Pure Python, no Home Assistant and no Music Assistant imports: the ordering
and the "which episode did they mean" rules are testable on their own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .matching import MATCH_THRESHOLD, match_score, normalize

# Episode titles are long and descriptive ("Ironman, Teil 2: Der Sturz"), so a
# keyword search may only cover a small part of the title.
EPISODE_MATCH_THRESHOLD = 0.45


@dataclass(frozen=True, slots=True)
class Episode:
    """One podcast episode, reduced to what a voice answer needs."""

    name: str
    uri: str
    position: int = 0
    released: str | None = None
    duration: int = 0
    fully_played: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Small payload for tool responses."""
        payload: dict[str, Any] = {"titel": self.name, "uri": self.uri}
        if self.released:
            payload["datum"] = self.released
        if self.duration:
            payload["dauer_min"] = round(self.duration / 60)
        if self.fully_played:
            payload["gehoert"] = True
        return payload


def to_episodes(items: Sequence[Mapping[str, Any]]) -> list[Episode]:
    """Build episodes from the dicts the Music Assistant bridge returns."""
    episodes: list[Episode] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        uri = item.get("uri")
        if not name or not uri:
            continue
        episodes.append(
            Episode(
                name=str(name),
                uri=str(uri),
                position=int(item.get("position") or 0),
                released=str(item["released"]) if item.get("released") else None,
                duration=int(item.get("duration") or 0),
                fully_played=bool(item.get("fully_played")),
            )
        )
    return episodes


def newest_first(episodes: Sequence[Episode]) -> list[Episode]:
    """Sort by release date, falling back to the feed position."""
    return sorted(
        episodes,
        key=lambda episode: (episode.released or "", episode.position),
        reverse=True,
    )


def matching(
    episodes: Sequence[Episode],
    query: str,
    threshold: float = EPISODE_MATCH_THRESHOLD,
) -> list[Episode]:
    """Episodes whose title matches ``query``, best first.

    A spoken keyword ("die Ironman-Folge") is usually a substring of a much
    longer title, so a plain containment hit counts as a strong match.
    """
    if not query:
        return newest_first(episodes)

    scored: list[tuple[float, int, Episode]] = []
    for index, episode in enumerate(episodes):
        score = max(
            match_score(query, episode.name), _keyword_score(query, episode.name)
        )
        if score >= threshold:
            scored.append((score, -index, episode))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return [episode for _, _, episode in scored]


def _keyword_score(query: str, title: str) -> float:
    """How much of the query appears in the title, word by word."""
    # Short words are noise ("der", "von") — except numbers, which are exactly
    # what separates "Teil 1" from "Teil 2".
    query_words = [
        word for word in normalize(query).split() if len(word) > 2 or word.isdigit()
    ]
    if not query_words:
        return 0.0
    title_text = normalize(title)
    title_words = set(title_text.split())
    hits = sum(1 for word in query_words if word in title_words or word in title_text)
    if not hits:
        return 0.0
    # All words present is as good as an exact match; partial coverage scales.
    return MATCH_THRESHOLD + (1 - MATCH_THRESHOLD) * (hits / len(query_words))
