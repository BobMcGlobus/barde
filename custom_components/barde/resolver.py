"""Player resolution — which speaker does the user mean.

Resolution order, first hit wins:

1. the player named in the tool call (fuzzy, against friendly names, entity
   aliases and area names)
2. the area the command was spoken from
3. the only player that is currently playing
4. the configured default player

Everything downstream works with ``entity_id`` — never ``device_id``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from .const import (
    CONVERSATION_ASSISTANT,
    MA_DOMAIN,
    MEDIA_PLAYER_DOMAIN,
)
from .exceptions import PlayerNotFound
from .matching import best_match

if TYPE_CHECKING:
    from homeassistant.helpers import llm

    from .api import BardeRuntime

_LOGGER = logging.getLogger(__name__)

_IDLE_STATES = {STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN, "standby"}
STATE_PLAYING = "playing"


def _should_expose(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether the entity is exposed to Assist (best effort)."""
    try:
        from homeassistant.components.homeassistant.exposed_entities import (
            async_should_expose,
        )

        return async_should_expose(hass, CONVERSATION_ASSISTANT, entity_id)
    except Exception:  # noqa: BLE001 - never fail a voice turn over this
        _LOGGER.debug("Exposure check unavailable, treating %s as exposed", entity_id)
        return True


def ma_players(runtime: BardeRuntime) -> list[str]:
    """All Music Assistant media_player entity ids Barde may control."""
    hass = runtime.hass
    registry = er.async_get(hass)
    entity_ids: list[str] = []
    for entry in registry.entities.values():
        if entry.domain != MEDIA_PLAYER_DOMAIN or entry.platform != MA_DOMAIN:
            continue
        if entry.disabled_by is not None or entry.hidden_by is not None:
            continue
        if entry.config_entry_id and entry.config_entry_id != runtime.ma_entry_id:
            continue
        if runtime.respect_exposure and not _should_expose(hass, entry.entity_id):
            continue
        entity_ids.append(entry.entity_id)
    return sorted(entity_ids)


def area_id_of(hass: HomeAssistant, entity_id: str) -> str | None:
    """Area of an entity, falling back to the area of its device."""
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id:
        device = dr.async_get(hass).async_get(entry.device_id)
        if device:
            return device.area_id
    return None


def area_name(hass: HomeAssistant, area_id: str | None) -> str | None:
    """Human readable area name."""
    if not area_id:
        return None
    area = ar.async_get(hass).async_get_area(area_id)
    return area.name if area else None


def aliases_of(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Every name this player can plausibly be called by."""
    names: list[str] = []
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry:
        names.extend(entry.aliases)
        if entry.name:
            names.append(entry.name)
        if entry.original_name:
            names.append(entry.original_name)
    state = hass.states.get(entity_id)
    if state and (friendly := state.attributes.get("friendly_name")):
        names.append(str(friendly))
    area_id = area_id_of(hass, entity_id)
    if area_id and (area := ar.async_get(hass).async_get_area(area_id)):
        names.append(area.name)
        names.extend(area.aliases)
    return [name for name in names if name]


def label(runtime: BardeRuntime, entity_id: str) -> str:
    """Short name for tool responses — the room, unless it is ambiguous."""
    hass = runtime.hass
    area_id = area_id_of(hass, entity_id)
    name = area_name(hass, area_id)
    if name:
        siblings = [
            other for other in ma_players(runtime) if area_id_of(hass, other) == area_id
        ]
        if len(siblings) <= 1:
            return name
    state = hass.states.get(entity_id)
    if state and (friendly := state.attributes.get("friendly_name")):
        return str(friendly)
    return entity_id


def is_playing(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether the player is currently playing."""
    state = hass.states.get(entity_id)
    return state is not None and state.state == STATE_PLAYING


def is_active(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether the player is on (playing, paused, idle-but-awake)."""
    state = hass.states.get(entity_id)
    return state is not None and state.state not in _IDLE_STATES


def resolve_player(
    runtime: BardeRuntime,
    name: str | None = None,
    llm_context: llm.LLMContext | None = None,
    prefer_playing: bool = False,
) -> str:
    """Return the entity id of the player the request is about."""
    hass = runtime.hass
    candidates = ma_players(runtime)
    if not candidates:
        raise PlayerNotFound(
            "Keine Music-Assistant-Player verfügbar. Läuft Music Assistant?"
        )

    if name:
        resolved = match_player(runtime, name, candidates)
        if resolved is None:
            raise PlayerNotFound(
                f"Kein Lautsprecher passt zu '{name}'",
                [label(runtime, entity_id) for entity_id in candidates],
            )
        return resolved

    if prefer_playing and (playing := _only_playing(hass, candidates)):
        return playing

    if spoken_from := _area_player(runtime, candidates, llm_context):
        return spoken_from

    if playing := _only_playing(hass, candidates):
        return playing

    default_player = runtime.default_player
    if default_player and default_player in candidates:
        return default_player
    if default_player and hass.states.get(default_player):
        # Configured explicitly — honour it even if exposure filtered it out.
        return default_player

    raise PlayerNotFound(
        "Kein Lautsprecher erkennbar — bitte den Raum nennen",
        [label(runtime, entity_id) for entity_id in candidates],
    )


def match_player(
    runtime: BardeRuntime, name: str, candidates: list[str] | None = None
) -> str | None:
    """Fuzzy-match a spoken player or room name against the MA players."""
    hass = runtime.hass
    entity_ids = candidates if candidates is not None else ma_players(runtime)
    if name in entity_ids:
        return name
    aliases = {entity_id: aliases_of(hass, entity_id) for entity_id in entity_ids}
    match = best_match(name, aliases)
    return match[0] if match else None


def resolve_players(runtime: BardeRuntime, names: list[str]) -> list[str]:
    """Resolve a list of spoken names, raising on the first miss."""
    candidates = ma_players(runtime)
    resolved: list[str] = []
    for name in names:
        entity_id = match_player(runtime, name, candidates)
        if entity_id is None:
            raise PlayerNotFound(
                f"Kein Lautsprecher passt zu '{name}'",
                [label(runtime, candidate) for candidate in candidates],
            )
        if entity_id not in resolved:
            resolved.append(entity_id)
    return resolved


def _only_playing(hass: HomeAssistant, candidates: list[str]) -> str | None:
    playing = [entity_id for entity_id in candidates if is_playing(hass, entity_id)]
    return playing[0] if len(playing) == 1 else None


def _area_player(
    runtime: BardeRuntime,
    candidates: list[str],
    llm_context: llm.LLMContext | None,
) -> str | None:
    """Return the MA player in the area the command was spoken from."""
    hass = runtime.hass
    device_id = getattr(llm_context, "device_id", None)
    if not device_id:
        return None
    device = dr.async_get(hass).async_get(device_id)
    if device is None or device.area_id is None:
        return None
    in_area = [
        entity_id
        for entity_id in candidates
        if area_id_of(hass, entity_id) == device.area_id
    ]
    if not in_area:
        return None
    for entity_id in in_area:
        if is_active(hass, entity_id):
            return entity_id
    return in_area[0]
