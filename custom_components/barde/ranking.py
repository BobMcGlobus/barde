"""Turn a Music Assistant search response into a ranked candidate list.

Pure Python (no Home Assistant imports) so the ranking rules are testable
on their own — they are the part that decides whether "spiel Rumours" starts
the album or a random cover version.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from .matching import match_score, normalize, strip_query_filler

# Response bucket -> media type. Music Assistant returns one list per type.
RESULT_BUCKETS: dict[str, str] = {
    "playlists": "playlist",
    "albums": "album",
    "artists": "artist",
    "tracks": "track",
    "radio": "radio",
    "audiobooks": "audiobook",
    "podcasts": "podcast",
}

# Used when the request did not name a media type. A spoken command rarely
# means a single track when an album or playlist of the same name exists, and
# it means spoken word only when nothing musical matches.
TYPE_PRIORITY: dict[str, int] = {
    "playlist": 6,
    "album": 5,
    "artist": 4,
    "track": 3,
    "radio": 2,
    "audiobook": 1,
    "podcast": 0,
}

LIBRARY_PROVIDER = "library"

_URI_RE = re.compile(r"^[a-z0-9_.-]+://\S+$", re.IGNORECASE)


def is_uri(value: str) -> bool:
    """Return True for values that are already a Music Assistant URI."""
    return bool(_URI_RE.match(value.strip()))


def provider_of(uri: str) -> str:
    """Extract the provider prefix of a MA URI (``spotify://album/x``)."""
    head, sep, _ = uri.partition("://")
    return head.lower() if sep else ""


@dataclass(frozen=True, slots=True)
class Candidate:
    """One search hit, reduced to what the tools actually need."""

    name: str
    uri: str
    media_type: str
    artist: str | None = None
    provider: str = ""
    favorite: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Small payload for tool responses — no artwork, no metadata blobs."""
        return {
            "name": self.name,
            "artist": self.artist,
            "typ": self.media_type,
            "uri": self.uri,
            "quelle": self.provider,
        }


def _artist_of(item: Mapping[str, Any]) -> str | None:
    artists = item.get("artists")
    if isinstance(artists, Sequence) and not isinstance(artists, str | bytes):
        for artist in artists:
            if isinstance(artist, Mapping) and artist.get("name"):
                return str(artist["name"])
    album = item.get("album")
    if isinstance(album, Mapping):
        return _artist_of(album)
    return None


def flatten(response: Mapping[str, Any] | None) -> list[Candidate]:
    """Flatten a ``music_assistant.search`` response into candidates."""
    if not response:
        return []
    candidates: list[Candidate] = []
    for bucket, media_type in RESULT_BUCKETS.items():
        items = response.get(bucket) or []
        if not isinstance(items, Sequence) or isinstance(items, str | bytes):
            continue
        for item in items:
            candidate = _to_candidate(item, media_type)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def _to_candidate(item: Any, fallback_type: str) -> Candidate | None:
    if not isinstance(item, Mapping):
        return None
    uri = item.get("uri")
    name = item.get("name")
    if not uri or not name:
        return None
    version = item.get("version")
    full_name = f"{name} ({version})" if version else str(name)
    return Candidate(
        name=full_name,
        uri=str(uri),
        media_type=str(item.get("media_type") or fallback_type),
        artist=_artist_of(item),
        provider=provider_of(str(uri)),
        favorite=bool(item.get("favorite")),
    )


def rank(
    candidates: Sequence[Candidate],
    query: str,
    media_type: str | None = None,
    provider_preference: Sequence[str] = (),
    artist: str | None = None,
) -> list[Candidate]:
    """Order candidates best-first.

    Precedence (highest first): exact name hit, requested media type, default
    type order, requested artist, provider preference, library over streaming,
    name similarity. Ties keep the order Music Assistant returned.
    """
    normalized_query = normalize(query)
    preferences = [provider.lower() for provider in provider_preference]

    def sort_key(indexed: tuple[int, Candidate]) -> tuple:
        index, candidate = indexed
        try:
            provider_rank = len(preferences) - preferences.index(candidate.provider)
        except ValueError:
            provider_rank = 0
        return (
            int(normalize(candidate.name) == normalized_query),
            int(media_type is not None and candidate.media_type == media_type),
            TYPE_PRIORITY.get(candidate.media_type, 0),
            _artist_bonus(candidate, artist),
            provider_rank,
            int(candidate.provider == LIBRARY_PROVIDER),
            int(candidate.favorite),
            match_score(query, candidate.name),
            -index,
        )

    return [
        candidate
        for _, candidate in sorted(enumerate(candidates), key=sort_key, reverse=True)
    ]


def search_attempts(
    query: str, media_type: str | None, artist: str | None
) -> list[tuple[str, str | None, str | None]]:
    """Plan the searches for one play request, most specific first.

    Voice queries carry noise the library does not: a media type the model
    guessed ("Hazbin Hotel Songs" as a *track*), an artist that is not credited
    that way, or words like "Songs" that belong to the sentence rather than to
    the title. Each of those gets dropped in turn — the caller only runs the
    next attempt when the previous one came back empty.
    """
    attempts: list[tuple[str, str | None, str | None]] = [(query, media_type, artist)]
    if media_type:
        attempts.append((query, None, artist))
    if artist:
        attempts.append((query, None, None))
    cleaned = strip_query_filler(query)
    if cleaned and cleaned != query:
        attempts.append((cleaned, None, None))
    return attempts


def _artist_bonus(candidate: Candidate, artist: str | None) -> int:
    if not artist or not candidate.artist:
        return 0
    return int(match_score(artist, candidate.artist) >= 0.8)
