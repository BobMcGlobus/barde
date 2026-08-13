"""musik_suchen — look without playing."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..const import MEDIA_TYPES
from ..ranking import flatten, rank
from .base import BardeTool


class SearchTool(BardeTool):
    """Search the library and the streaming providers."""

    name = "musik_suchen"
    description = (
        "Sucht Musik, Hörbücher und Podcasts, ohne sie abzuspielen. Für Fragen "
        "wie 'was hast du von Portishead', 'welche Hörbücher gibt es', "
        "'welche Alben gibt es von X' oder wenn unklar ist, was "
        "der Nutzer meint und du nachfragen willst. Gibt pro Treffer Name, "
        "Künstler, Typ und uri zurück. Die uri kann direkt als query an "
        "musik_abspielen übergeben werden, um genau diesen Treffer zu "
        "starten. library_only=true beschränkt auf die eigene Bibliothek."
    )
    parameters = vol.Schema(
        {
            vol.Required("query"): str,
            vol.Optional("media_type"): vol.In(MEDIA_TYPES),
            vol.Optional("artist"): str,
            vol.Optional("limit", default=5): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=15)
            ),
            vol.Optional("library_only", default=False): bool,
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        query: str = kwargs["query"]
        media_type: str | None = kwargs.get("media_type")
        artist: str | None = kwargs.get("artist")
        limit: int = kwargs.get("limit", 5)

        response = await runtime.ma.search(
            query,
            media_types=[media_type] if media_type else MEDIA_TYPES,
            artist=artist,
            limit=max(limit, 10),
            library_only=kwargs.get("library_only", False),
        )
        ranked = rank(
            flatten(response),
            query,
            media_type=media_type,
            provider_preference=runtime.provider_preference,
            artist=artist,
        )
        return {
            "treffer": [candidate.as_dict() for candidate in ranked[:limit]],
            "anzahl": len(ranked),
        }
