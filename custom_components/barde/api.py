"""The Barde LLM API — runtime state and the api_prompt.

The prompt is rebuilt per conversation. It is the single biggest lever on hit
rate, and it is also the place where token budget is spent, so it stays under
roughly 400 tokens: speaker states (live), playlist names (cached), a handful
of rules.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import llm

from .const import (
    CONF_CONTEXT_TTL,
    CONF_DEFAULT_PLAYER,
    CONF_EXPOSE_FAVORITES,
    CONF_EXPOSE_PLAYLISTS,
    CONF_PROVIDER_PREFERENCE,
    CONF_RESPECT_EXPOSURE,
    CONF_VOLUME_STEP,
    DEFAULT_CONTEXT_TTL,
    DEFAULT_EXPOSE_FAVORITES,
    DEFAULT_EXPOSE_PLAYLISTS,
    DEFAULT_PROVIDER_PREFERENCE,
    DEFAULT_RESPECT_EXPOSURE,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
    MAX_PROMPT_PLAYERS,
)
from .context import LibraryContext
from .finder import MediaFinder
from .ma import MusicAssistantBridge
from .resolver import label, ma_players
from .tools import build_tools

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

ROLE = "Du bist der Barde des Hauses und steuerst Music Assistant."

RULES = (
    "Wenn kein Raum genannt wird, nimm den Raum, aus dem gesprochen wurde.\n"
    "Frage nicht nach, wenn ein plausibler Treffer existiert — spiele ihn "
    "und sage, was du gewählt hast.\n"
    "Für alles rund um Musik nutze die Barde-Tools, nicht die allgemeinen "
    "Medien-Intents von Assist."
)


class BardeRuntime:
    """Everything the tools need: options, the MA bridge, the library cache."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, ma_entry_id: str
    ) -> None:
        """Set up the runtime for one Barde config entry."""
        self.hass = hass
        self.entry = entry
        self.ma_entry_id = ma_entry_id
        self.ma = MusicAssistantBridge(hass, ma_entry_id)
        self.library = LibraryContext(self)
        self.finder = MediaFinder(self)

    def _option(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def default_player(self) -> str | None:
        """Fallback player when no room can be derived."""
        return self._option(CONF_DEFAULT_PLAYER, None)

    @property
    def expose_playlists(self) -> bool:
        """Whether playlist names go into the prompt."""
        return bool(self._option(CONF_EXPOSE_PLAYLISTS, DEFAULT_EXPOSE_PLAYLISTS))

    @property
    def expose_favorites(self) -> bool:
        """Whether favourite artists go into the prompt."""
        return bool(self._option(CONF_EXPOSE_FAVORITES, DEFAULT_EXPOSE_FAVORITES))

    @property
    def context_ttl(self) -> int:
        """Library cache lifetime in minutes."""
        return int(self._option(CONF_CONTEXT_TTL, DEFAULT_CONTEXT_TTL))

    @property
    def provider_preference(self) -> list[str]:
        """Provider order used to break ranking ties."""
        return list(self._option(CONF_PROVIDER_PREFERENCE, DEFAULT_PROVIDER_PREFERENCE))

    @property
    def respect_exposure(self) -> bool:
        """Whether players hidden from Assist stay off limits."""
        return bool(self._option(CONF_RESPECT_EXPOSURE, DEFAULT_RESPECT_EXPOSURE))

    @property
    def volume_step(self) -> int:
        """Percentage points per 'lauter'/'leiser'."""
        return int(self._option(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP))


class BardeAPI(llm.API):
    """LLM API exposing the Barde tools, selectable per conversation agent."""

    def __init__(self, hass: HomeAssistant, runtime: BardeRuntime) -> None:
        """Register under the domain id so it shows up as 'Barde'."""
        super().__init__(hass=hass, id=DOMAIN, name="Barde")
        self.runtime = runtime

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Build prompt and tool set for one conversation."""
        return llm.APIInstance(
            api=self,
            api_prompt=await self.async_build_prompt(),
            llm_context=llm_context,
            tools=build_tools(self.runtime),
        )

    async def async_build_prompt(self) -> str:
        """Assemble the api_prompt."""
        runtime = self.runtime
        parts = [ROLE, _players_block(runtime), RULES]

        if runtime.expose_playlists:
            playlists = await runtime.library.async_playlists()
            if playlists:
                parts.append("Bekannte Playlists: " + ", ".join(playlists))
        if runtime.expose_favorites:
            favorites = await runtime.library.async_favorite_artists()
            if favorites:
                parts.append("Lieblingskünstler: " + ", ".join(favorites))

        return "\n\n".join(part for part in parts if part)


def _players_block(runtime: BardeRuntime) -> str:
    """Speaker list with live states, read straight from the state machine."""
    entity_ids = ma_players(runtime)
    if not entity_ids:
        return "Aktuell sind keine Lautsprecher verfügbar."

    labels = [label(runtime, entity_id) for entity_id in entity_ids]
    if len(entity_ids) > MAX_PROMPT_PLAYERS:
        return "Verfügbare Lautsprecher: " + ", ".join(labels)

    lines = [
        f"  {name} → {_describe(runtime, entity_id)}"
        for name, entity_id in zip(labels, entity_ids, strict=True)
    ]
    return "Verfügbare Lautsprecher (Raum → Zustand):\n" + "\n".join(lines)


def _describe(runtime: BardeRuntime, entity_id: str) -> str:
    state = runtime.hass.states.get(entity_id)
    if state is None:
        return "unbekannt"

    attributes = state.attributes
    title = attributes.get("media_title")
    artist = attributes.get("media_artist")
    now_playing = f'"{title}"' if title else ""
    if title and artist:
        now_playing = f'"{title}" ({artist})'

    if state.state == "playing":
        text = f"spielt {now_playing}".strip()
    elif state.state == "paused":
        text = f"pausiert {now_playing}".strip()
    elif state.state in ("off", "standby"):
        text = "aus"
    elif state.state == "unavailable":
        text = "nicht erreichbar"
    else:
        text = "an, nichts läuft"

    members = [
        member
        for member in attributes.get("group_members") or []
        if member != entity_id
    ]
    if members:
        joined = ", ".join(label(runtime, member) for member in members)
        text = f"{text}, gruppiert mit {joined}"
    return text
