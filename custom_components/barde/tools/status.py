"""was_laeuft — read player states, no service call needed."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..resolver import is_active, label, ma_players, resolve_player
from .base import BardeTool

ATTR_GROUP_MEMBERS = "group_members"


class StatusTool(BardeTool):
    """What is playing where."""

    name = "was_laeuft"
    description = (
        "Sagt, was gerade läuft: Titel, Künstler, Lautstärke und Gruppierung. "
        "Ohne player werden alle Lautsprecher zurückgegeben, auf denen etwas "
        "läuft — damit ist 'läuft irgendwo noch Musik?' in einem Schritt "
        "beantwortet. queue_anzeigen=true holt zusätzlich die Länge der "
        "Warteschlange und den nächsten Titel."
    )
    parameters = vol.Schema(
        {
            vol.Optional("player"): str,
            vol.Optional("queue_anzeigen", default=False): bool,
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        with_queue: bool = kwargs.get("queue_anzeigen", False)
        player: str | None = kwargs.get("player")

        if player:
            entity_id = resolve_player(runtime, player, llm_context)
            return await self._async_describe(entity_id, with_queue)

        active = [
            entity_id
            for entity_id in ma_players(runtime)
            if is_active(runtime.hass, entity_id)
        ]
        if not active:
            return {"laeuft": False, "hinweis": "Es läuft gerade keine Musik"}
        return {
            "laeuft": True,
            "player": [
                await self._async_describe(entity_id, with_queue)
                for entity_id in active
            ],
        }

    async def _async_describe(self, entity_id: str, with_queue: bool) -> dict[str, Any]:
        runtime = self.runtime
        state = runtime.hass.states.get(entity_id)
        if state is None:
            return {"player": label(runtime, entity_id), "status": "unbekannt"}

        attributes = state.attributes
        result: dict[str, Any] = {
            "player": label(runtime, entity_id),
            "status": state.state,
        }
        for key, attribute in (
            ("titel", "media_title"),
            ("künstler", "media_artist"),
            ("album", "media_album_name"),
        ):
            if value := attributes.get(attribute):
                result[key] = str(value)
        if (volume := attributes.get("volume_level")) is not None:
            result["lautstärke"] = round(float(volume) * 100)
        if attributes.get("is_volume_muted"):
            result["stumm"] = True
        if (remaining := runtime.timers.remaining(entity_id)) is not None:
            result["einschlaftimer_min"] = remaining
        if members := attributes.get(ATTR_GROUP_MEMBERS):
            group = [
                label(runtime, member) for member in members if member != entity_id
            ]
            if group:
                result["gruppiert_mit"] = group

        if with_queue:
            result.update(await self._async_queue(entity_id))
        return result

    async def _async_queue(self, entity_id: str) -> dict[str, Any]:
        queue = await self.runtime.ma.get_queue(entity_id)
        result: dict[str, Any] = {}
        if (items := queue.get("items")) is not None:
            result["queue_länge"] = items
        next_item = queue.get("next_item")
        if isinstance(next_item, dict) and next_item.get("name"):
            result["als_nächstes"] = str(next_item["name"])
        return result
