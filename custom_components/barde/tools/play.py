"""musik_abspielen — search, rank, play."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..const import DEFAULT_SEARCH_LIMIT, ENQUEUE_MODES, MEDIA_TYPES
from ..exceptions import NothingFound
from ..ma import async_media_player
from ..ranking import Candidate, flatten, is_uri, provider_of, rank
from ..resolver import label, resolve_player
from .base import BardeTool


class PlayTool(BardeTool):
    """Play something, somewhere."""

    name = "musik_abspielen"
    description = (
        "Spielt Musik auf einem Lautsprecher ab. Nutze dieses Tool für jede "
        "Anfrage, Musik zu starten — 'spiel Rumours', 'leg die Kochmusik auf', "
        "'spiel Daft Punk in der Küche', 'mach Radio an'. query ist der "
        "gesuchte Name (Song, Album, Künstler, Playlist oder Sender). "
        "media_type nur setzen, wenn der Nutzer den Typ nennt ('das Album X'). "
        "artist zur Unterscheidung ('Rumours von Fleetwood Mac'). player ist "
        "der Raum- oder Lautsprechername im Klartext; weglassen, wenn kein "
        "Raum genannt wurde — dann wird der Raum des Sprechers genommen. "
        "enqueue='next' oder 'add' hängt an die laufende Wiedergabeliste an, "
        "statt sie zu ersetzen. radio_mode=true spielt nach dem Treffer "
        "endlos ähnliche Musik weiter ('spiel was in der Richtung')."
    )
    parameters = vol.Schema(
        {
            vol.Required("query"): str,
            vol.Optional("media_type"): vol.In(MEDIA_TYPES),
            vol.Optional("artist"): str,
            vol.Optional("player"): str,
            vol.Optional("enqueue", default="replace"): vol.In(ENQUEUE_MODES),
            vol.Optional("radio_mode", default=False): bool,
            vol.Optional("shuffle", default=False): bool,
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        query: str = kwargs["query"]
        media_type: str | None = kwargs.get("media_type")
        artist: str | None = kwargs.get("artist")

        entity_id = resolve_player(runtime, kwargs.get("player"), llm_context)

        if is_uri(query):
            chosen = Candidate(
                name=query,
                uri=query,
                media_type=media_type or "",
                artist=artist,
                provider=provider_of(query),
            )
            alternatives = 0
        else:
            response = await runtime.ma.search(
                query,
                media_types=[media_type] if media_type else MEDIA_TYPES,
                artist=artist,
                limit=DEFAULT_SEARCH_LIMIT,
            )
            ranked = rank(
                flatten(response),
                query,
                media_type=media_type,
                provider_preference=runtime.provider_preference,
                artist=artist,
            )
            if not ranked:
                raise NothingFound(
                    f"Nichts gefunden für '{query}'"
                    + (f" von {artist}" if artist else "")
                )
            chosen = ranked[0]
            alternatives = len(ranked) - 1

        await runtime.ma.play_media(
            entity_id,
            chosen.uri,
            media_type=chosen.media_type or None,
            enqueue=kwargs.get("enqueue", "replace"),
            radio_mode=kwargs.get("radio_mode", False),
        )

        if kwargs.get("shuffle"):
            await async_media_player(
                runtime.hass, "shuffle_set", entity_id, shuffle=True
            )

        result: dict[str, Any] = {
            "gespielt": chosen.name,
            "typ": chosen.media_type,
            "player": label(runtime, entity_id),
            "quelle": chosen.provider,
            "alternativen": alternatives,
        }
        if chosen.artist:
            result["künstler"] = chosen.artist
        return result
