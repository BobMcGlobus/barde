"""musik_suchen — look without playing."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..const import MEDIA_TYPES
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
        limit: int = kwargs.get("limit", 5)

        ranked = await runtime.finder.async_find(
            query,
            media_type=kwargs.get("media_type"),
            artist=kwargs.get("artist"),
            library_only=kwargs.get("library_only", False),
        )
        return {
            "treffer": [candidate.as_dict() for candidate in ranked[:limit]],
            "anzahl": len(ranked),
        }
