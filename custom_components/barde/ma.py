"""Thin facade over the Music Assistant service actions.

Barde deliberately talks to Music Assistant through the documented
``music_assistant.*`` actions instead of opening its own websocket or reaching
into ``entry.runtime_data`` of the MA integration — no second token, no private
API that breaks on the next HA release.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from .const import MA_DOMAIN, MEDIA_PLAYER_DOMAIN, SERVICE_TIMEOUT
from .exceptions import BardeError

_LOGGER = logging.getLogger(__name__)

ATTR_CONFIG_ENTRY_ID = "config_entry_id"


class MusicAssistantBridge:
    """Service-call wrapper around one Music Assistant config entry."""

    def __init__(self, hass: HomeAssistant, config_entry_id: str) -> None:
        """Bind the bridge to the MA config entry its actions target."""
        self.hass = hass
        self.config_entry_id = config_entry_id

    async def search(
        self,
        name: str,
        media_types: list[str] | None = None,
        artist: str | None = None,
        album: str | None = None,
        limit: int = 10,
        library_only: bool = False,
    ) -> dict[str, Any]:
        """Run ``music_assistant.search`` and return the raw response."""
        data: dict[str, Any] = {
            ATTR_CONFIG_ENTRY_ID: self.config_entry_id,
            "name": name,
            "limit": limit,
        }
        if media_types:
            data["media_type"] = media_types
        if artist:
            data["artist"] = artist
        if album:
            data["album"] = album
        if library_only:
            data["library_only"] = True
        return await self._call("search", data, response=True)

    async def get_library(
        self,
        media_type: str,
        favorite: bool = False,
        limit: int = 100,
        order_by: str | None = None,
    ) -> dict[str, Any]:
        """Run ``music_assistant.get_library``."""
        data: dict[str, Any] = {
            ATTR_CONFIG_ENTRY_ID: self.config_entry_id,
            "media_type": media_type,
            "limit": limit,
        }
        if favorite:
            data["favorite"] = True
        if order_by:
            data["order_by"] = order_by
        return await self._call("get_library", data, response=True)

    async def play_media(
        self,
        entity_id: str,
        media_id: str,
        media_type: str | None = None,
        enqueue: str = "replace",
        radio_mode: bool = False,
        artist: str | None = None,
        album: str | None = None,
    ) -> None:
        """Run ``music_assistant.play_media`` on one player."""
        data: dict[str, Any] = {
            "entity_id": entity_id,
            "media_id": media_id,
            "enqueue": enqueue,
        }
        if media_type:
            data["media_type"] = media_type
        if radio_mode:
            data["radio_mode"] = True
        if artist:
            data["artist"] = artist
        if album:
            data["album"] = album
        await self._call("play_media", data)

    async def transfer_queue(
        self,
        entity_id: str,
        source_player: str | None = None,
        auto_play: bool = True,
    ) -> None:
        """Move the active queue onto ``entity_id``."""
        data: dict[str, Any] = {"entity_id": entity_id, "auto_play": auto_play}
        if source_player:
            data["source_player"] = source_player
        await self._call("transfer_queue", data)

    async def get_queue(self, entity_id: str) -> dict[str, Any]:
        """Return the queue details of one player.

        Entity actions wrap their response in ``{entity_id: payload}`` — the
        caller only cares about the payload.
        """
        response = await self._call(
            "get_queue", {"entity_id": entity_id}, response=True
        )
        payload = response.get(entity_id)
        if isinstance(payload, dict):
            return payload
        if len(response) == 1:
            only = next(iter(response.values()))
            if isinstance(only, dict):
                return only
        return response

    async def podcast_episodes(self, uri: str) -> list[dict[str, Any]]:
        """Episodes of one podcast, as plain dicts.

        The only place Barde reaches past the service actions. There is no
        action for episodes — ``music_assistant.search`` cannot return them and
        ``get_library`` does not list them — so this borrows the client the
        Music Assistant integration already holds. That is private API: it is
        contained here, guarded, and every failure becomes a BardeError.
        """
        client = self._client()
        try:
            podcast = await client.music.get_item_by_uri(uri)
            episodes = await client.music.get_podcast_episodes(
                podcast.item_id, podcast.provider
            )
        except Exception as err:  # noqa: BLE001 - foreign library, foreign errors
            _LOGGER.debug("Episode lookup for %s failed: %s", uri, err)
            raise BardeError(
                f"Folgen konnten nicht geladen werden ({type(err).__name__}: {err})"
            ) from err
        return [_episode_dict(episode) for episode in episodes]

    def _client(self) -> Any:
        """Return the Music Assistant client of the entry we target."""
        entry = self.hass.config_entries.async_get_entry(self.config_entry_id)
        client = getattr(getattr(entry, "runtime_data", None), "mass", None)
        if client is None:
            raise BardeError(
                "Kein Zugriff auf Music Assistant — läuft die Integration?"
            )
        return client

    async def _call(
        self, service: str, data: dict[str, Any], response: bool = False
    ) -> dict[str, Any]:
        """Call a MA action, mapping timeouts and HA errors to BardeError."""
        return await _async_call(self.hass, MA_DOMAIN, service, data, response=response)


def _episode_dict(episode: Any) -> dict[str, Any]:
    """Flatten a PodcastEpisode into the few fields Barde uses."""
    released = getattr(getattr(episode, "metadata", None), "release_date", None)
    return {
        "name": getattr(episode, "name", None),
        "uri": getattr(episode, "uri", None),
        "position": getattr(episode, "position", 0),
        "duration": getattr(episode, "duration", 0),
        "fully_played": bool(getattr(episode, "fully_played", False)),
        "released": released.isoformat() if hasattr(released, "isoformat") else None,
    }


async def async_media_player(
    hass: HomeAssistant, service: str, entity_id: str, **data: Any
) -> None:
    """Call a plain ``media_player`` service on one entity."""
    await _async_call(
        hass, MEDIA_PLAYER_DOMAIN, service, {"entity_id": entity_id, **data}
    )


async def _async_call(
    hass: HomeAssistant,
    domain: str,
    service: str,
    data: dict[str, Any],
    response: bool = False,
) -> dict[str, Any]:
    try:
        async with asyncio.timeout(SERVICE_TIMEOUT):
            result = await hass.services.async_call(
                domain,
                service,
                data,
                blocking=True,
                return_response=response,
            )
    except TimeoutError as err:
        _LOGGER.warning("%s.%s timed out after %ss", domain, service, SERVICE_TIMEOUT)
        raise BardeError(
            f"{domain}.{service} hat nicht innerhalb von "
            f"{SERVICE_TIMEOUT} Sekunden geantwortet"
        ) from err
    except vol.Invalid as err:
        _LOGGER.debug("%s.%s rejected %s: %s", domain, service, data, err)
        raise BardeError(f"{domain}.{service}: ungültige Parameter ({err})") from err
    except HomeAssistantError as err:
        _LOGGER.debug("%s.%s failed: %s", domain, service, err)
        raise BardeError(f"{domain}.{service}: {err}") from err
    except Exception as err:  # noqa: BLE001
        # music_assistant.search & friends are not wrapped on the MA side, so a
        # MusicAssistantError arrives here raw — and raw is fatal for the run.
        _LOGGER.exception("%s.%s raised unexpectedly for %s", domain, service, data)
        raise BardeError(f"{domain}.{service}: {type(err).__name__}: {err}") from err
    return result if isinstance(result, dict) else {}
