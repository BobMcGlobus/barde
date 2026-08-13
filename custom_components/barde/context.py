"""Library context for the api_prompt.

Knowing the playlist names is the difference between "leg die Kochmusik auf"
working and the model searching every streaming provider for the word
"Kochmusik". The library barely changes, so it is cached for ``context_ttl``
minutes; player states are read live and never cached.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from .const import (
    LIBRARY_FETCH_LIMIT,
    MAX_PROMPT_FAVORITES,
    MAX_PROMPT_PLAYLISTS,
)
from .exceptions import BardeError

if TYPE_CHECKING:
    from datetime import datetime

    from .api import BardeRuntime

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _CacheEntry:
    value: list[str]
    fetched_at: datetime


class LibraryContext:
    """TTL cache for the library names that go into the api_prompt."""

    def __init__(self, runtime: BardeRuntime) -> None:
        """Create the cache for one Barde runtime."""
        self._runtime = runtime
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        """Drop the cache (called when options change)."""
        self._cache.clear()

    async def async_playlists(self) -> list[str]:
        """Playlist names, most recently played first, alphabetically listed."""
        return await self._async_cached(
            "playlists",
            media_type="playlist",
            favorite=False,
            order_by="last_played_desc",
            maximum=MAX_PROMPT_PLAYLISTS,
        )

    async def async_favorite_artists(self) -> list[str]:
        """Favourite artist names."""
        return await self._async_cached(
            "favorites",
            media_type="artist",
            favorite=True,
            order_by="play_count_desc",
            maximum=MAX_PROMPT_FAVORITES,
        )

    async def _async_cached(
        self,
        key: str,
        media_type: str,
        favorite: bool,
        order_by: str,
        maximum: int,
    ) -> list[str]:
        ttl = timedelta(minutes=self._runtime.context_ttl)
        now = dt_util.utcnow()
        cached = self._cache.get(key)
        if cached and now - cached.fetched_at < ttl:
            return cached.value

        async with self._lock:
            # Another turn may have refreshed while we waited for the lock.
            cached = self._cache.get(key)
            if cached and dt_util.utcnow() - cached.fetched_at < ttl:
                return cached.value
            names = await self._async_fetch(media_type, favorite, order_by, maximum)
            self._cache[key] = _CacheEntry(names, dt_util.utcnow())
            return names

    async def _async_fetch(
        self, media_type: str, favorite: bool, order_by: str, maximum: int
    ) -> list[str]:
        try:
            response = await self._runtime.ma.get_library(
                media_type,
                favorite=favorite,
                limit=LIBRARY_FETCH_LIMIT,
                order_by=order_by,
            )
        except BardeError as err:
            # A missing library block degrades the prompt, it must not break
            # the conversation.
            _LOGGER.debug("Library fetch for %s failed: %s", media_type, err)
            return []
        return _names(response, maximum)


def _names(response: dict[str, Any], maximum: int) -> list[str]:
    items = response.get("items") or []
    names: list[str] = []
    for item in items:
        if isinstance(item, dict) and (name := item.get("name")):
            text = str(name)
            if text not in names:
                names.append(text)
        if len(names) >= maximum:
            break
    return sorted(names, key=str.casefold)
