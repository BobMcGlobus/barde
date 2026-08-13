"""Turning a spoken wish into playable candidates.

Two sources, deliberately: the provider search of Music Assistant, and the
library itself. Provider search is a text query against Spotify, Tidal and
friends — it is good at music and bad at what the user actually said. The
library is small, local, and can be matched fuzzily right here, which is what
podcasts and audiobooks need: "Kack- und Sachgeschichten" only ever finds
"Kack & Sachgeschichten" when the comparison happens on our side.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .const import DEFAULT_SEARCH_LIMIT, LIBRARY_FETCH_LIMIT, MEDIA_TYPES
from .exceptions import BardeError
from .ranking import (
    Candidate,
    filter_by_name,
    flatten,
    from_library,
    rank,
    search_attempts,
)

if TYPE_CHECKING:
    from .api import BardeRuntime

_LOGGER = logging.getLogger(__name__)

# Media types that live in the library rather than on a streaming provider.
SPOKEN_TYPES = ("podcast", "audiobook")


class MediaFinder:
    """Finds media for the play and search tools."""

    def __init__(self, runtime: BardeRuntime) -> None:
        """Bind the finder to its runtime."""
        self.runtime = runtime

    async def async_find(
        self,
        query: str,
        media_type: str | None = None,
        artist: str | None = None,
        library_only: bool = False,
    ) -> list[Candidate]:
        """Best-first candidates for one request, or an empty list."""
        if media_type in SPOKEN_TYPES and (
            hits := await self.async_from_library(media_type, query)
        ):
            return hits

        for attempt_query, attempt_type, attempt_artist in search_attempts(
            query, media_type, artist
        ):
            hits = await self._async_search(
                attempt_query, attempt_type, attempt_artist, library_only
            )
            if hits:
                return hits

        # Nothing musical matched and the request named no type: the wish may
        # have been spoken word after all.
        if media_type is None:
            for spoken in SPOKEN_TYPES:
                if hits := await self.async_from_library(spoken, query):
                    return hits
        return []

    async def async_from_library(self, media_type: str, query: str) -> list[Candidate]:
        """Match ``query`` against the library entries of one media type."""
        try:
            response = await self.runtime.ma.get_library(
                media_type, limit=LIBRARY_FETCH_LIMIT
            )
        except BardeError as err:
            _LOGGER.debug("Library lookup for %s failed: %s", media_type, err)
            return []
        return filter_by_name(from_library(response, media_type), query)

    async def _async_search(
        self,
        query: str,
        media_type: str | None,
        artist: str | None,
        library_only: bool,
    ) -> list[Candidate]:
        """Run one provider search and rank what comes back."""
        runtime = self.runtime
        response = await runtime.ma.search(
            query,
            media_types=[media_type] if media_type else MEDIA_TYPES,
            artist=artist,
            limit=DEFAULT_SEARCH_LIMIT,
            library_only=library_only,
        )
        return rank(
            flatten(response),
            query,
            media_type=media_type,
            provider_preference=runtime.provider_preference,
            artist=artist,
        )
