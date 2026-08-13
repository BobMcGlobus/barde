"""musik_steuern — transport and volume in one tool."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..exceptions import BardeError
from ..ma import async_media_player
from ..resolver import label, resolve_player
from .base import BardeTool

# action -> (media_player service, static service data)
_SIMPLE_ACTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "pause": ("media_pause", {}),
    "weiter": ("media_play", {}),
    "stop": ("media_stop", {}),
    "naechster": ("media_next_track", {}),
    "vorheriger": ("media_previous_track", {}),
    "stumm": ("volume_mute", {"is_volume_muted": True}),
    "laut": ("volume_mute", {"is_volume_muted": False}),
    "shuffle_an": ("shuffle_set", {"shuffle": True}),
    "shuffle_aus": ("shuffle_set", {"shuffle": False}),
    "wiederholen_an": ("repeat_set", {"repeat": "all"}),
    "wiederholen_aus": ("repeat_set", {"repeat": "off"}),
    "queue_leeren": ("clear_playlist", {}),
}

ACTIONS = [
    "pause",
    "weiter",
    "stop",
    "naechster",
    "vorheriger",
    "lautstaerke",
    "lauter",
    "leiser",
    "stumm",
    "laut",
    "shuffle_an",
    "shuffle_aus",
    "wiederholen_an",
    "wiederholen_aus",
    "queue_leeren",
]


class ControlTool(BardeTool):
    """Everything that steers what is already playing."""

    name = "musik_steuern"
    description = (
        "Steuert die laufende Wiedergabe: pause, weiter, stop, naechster, "
        "vorheriger, lautstaerke (mit wert 0-100), lauter, leiser, stumm, "
        "laut (Stummschaltung aufheben), shuffle_an, shuffle_aus, "
        "wiederholen_an, wiederholen_aus, queue_leeren. Für 'lauter'/'leiser' "
        "keinen wert angeben — es wird in festen Schritten geregelt. "
        "player weglassen, wenn kein Raum genannt wurde."
    )
    parameters = vol.Schema(
        {
            vol.Required("action"): vol.In(ACTIONS),
            vol.Optional("player"): str,
            vol.Optional("wert"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        action: str = kwargs["action"]
        entity_id = resolve_player(
            runtime,
            kwargs.get("player"),
            llm_context,
            prefer_playing=action not in ("lautstaerke", "stumm", "laut"),
        )
        result: dict[str, Any] = {
            "aktion": action,
            "player": label(runtime, entity_id),
        }

        if action == "lautstaerke":
            wert = kwargs.get("wert")
            if wert is None:
                raise BardeError("Für 'lautstaerke' fehlt der wert (0-100 Prozent)")
            await self._async_set_volume(entity_id, wert)
            result["lautstärke"] = wert
            return result

        if action in ("lauter", "leiser"):
            result["lautstärke"] = await self._async_step_volume(entity_id, action)
            return result

        service, data = _SIMPLE_ACTIONS[action]
        await async_media_player(runtime.hass, service, entity_id, **data)
        return result

    async def _async_set_volume(self, entity_id: str, percent: int) -> None:
        await async_media_player(
            self.runtime.hass,
            "volume_set",
            entity_id,
            volume_level=round(percent / 100, 2),
        )

    async def _async_step_volume(self, entity_id: str, action: str) -> int | None:
        """Relative volume step — Assist users never name absolute values."""
        step = self.runtime.volume_step
        state = self.runtime.hass.states.get(entity_id)
        current = state.attributes.get("volume_level") if state else None
        if current is None:
            # No volume reported: let the player do its own stepping.
            await async_media_player(
                self.runtime.hass,
                "volume_up" if action == "lauter" else "volume_down",
                entity_id,
            )
            return None
        delta = step if action == "lauter" else -step
        target = min(100, max(0, round(float(current) * 100) + delta))
        await self._async_set_volume(entity_id, target)
        return target
