"""podcast_folgen — list, find and play single podcast episodes."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..episodes import Episode, matching, newest_first, to_episodes
from ..exceptions import NothingFound
from ..ranking import Candidate
from ..resolver import label, resolve_player
from .base import BardeTool

MAX_EPISODES = 20


class EpisodesTool(BardeTool):
    """Everything that is about a *single* episode of a podcast."""

    name = "podcast_folgen"
    description = (
        "Listet die Folgen eines Podcasts auf, sucht eine bestimmte Folge oder "
        "spielt sie ab. Nutze dieses Tool immer, wenn es um eine einzelne "
        "Folge geht: 'spiel die neueste Folge von <Podcast>' → "
        "abspielen=true; 'nenn mir die letzten zehn Folgen' → anzahl=10; "
        "'such die Ironman-Folge von <Podcast> raus' → suche='Ironman'; "
        "'spiel die Ironman-Folge' → suche='Ironman', abspielen=true. "
        "Ohne suche sind die Folgen nach Datum sortiert, die neueste zuerst. "
        "Für einen ganzen Podcast ohne bestimmte Folge nimm musik_abspielen."
    )
    parameters = vol.Schema(
        {
            vol.Required("podcast"): str,
            vol.Optional("suche"): str,
            vol.Optional("anzahl", default=5): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=MAX_EPISODES)
            ),
            vol.Optional("abspielen", default=False): bool,
            vol.Optional("player"): str,
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        wanted: str = kwargs["podcast"]
        search: str | None = kwargs.get("suche")
        count: int = kwargs.get("anzahl", 5)

        podcast = await self._async_resolve_podcast(wanted)
        episodes = to_episodes(await runtime.ma.podcast_episodes(podcast.uri))
        if not episodes:
            raise NothingFound(f"'{podcast.name}' hat keine abrufbaren Folgen")

        found = matching(episodes, search) if search else newest_first(episodes)
        if not found:
            raise NothingFound(f"Keine Folge von '{podcast.name}' passt zu '{search}'")

        if kwargs.get("abspielen"):
            return await self._async_play(found[0], podcast.name, kwargs, llm_context)

        return {
            "podcast": podcast.name,
            "folgen": [episode.as_dict() for episode in found[:count]],
            "anzahl": len(found),
        }

    async def _async_resolve_podcast(self, wanted: str) -> Candidate:
        """Find the podcast in the library, or say which ones exist."""
        runtime = self.runtime
        hits = await runtime.finder.async_from_library("podcast", wanted)
        if hits:
            return hits[0]
        available = await runtime.finder.async_library_items("podcast")
        raise NothingFound(
            f"Kein Podcast namens '{wanted}' in der Bibliothek"
            + (
                f" — vorhanden: {', '.join(item.name for item in available[:10])}"
                if available
                else ""
            )
        )

    async def _async_play(
        self,
        episode: Episode,
        podcast_name: str,
        kwargs: dict[str, Any],
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        runtime = self.runtime
        entity_id = resolve_player(runtime, kwargs.get("player"), llm_context)
        # No media_type: Music Assistant reads the episode URI itself, and
        # podcast_episode is not in the action's documented type list.
        await runtime.ma.play_media(entity_id, episode.uri, enqueue="replace")
        return {
            "gespielt": episode.name,
            "podcast": podcast_name,
            "typ": "podcast_folge",
            "player": label(runtime, entity_id),
            **({"datum": episode.released} if episode.released else {}),
        }
