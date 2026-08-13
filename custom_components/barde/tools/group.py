"""lautsprecher_gruppieren — join and unjoin speakers."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..exceptions import BardeError
from ..ma import async_media_player
from ..resolver import label, ma_players, resolve_player, resolve_players
from .base import BardeTool

ATTR_GROUP_MEMBERS = "group_members"


class GroupTool(BardeTool):
    """Multiroom — the part the built-in intents cannot do."""

    name = "lautsprecher_gruppieren"
    description = (
        "Verbindet Lautsprecher zu einer Gruppe oder trennt sie wieder. "
        "'mach im Wohnzimmer und Bad das gleiche' → aktion='gruppieren', "
        "hauptplayer='Wohnzimmer', player=['Bad']. Der hauptplayer gibt die "
        "Musik vor; ohne Angabe ist es der Raum des Sprechers. "
        "aktion='trennen' löst einzelne Lautsprecher aus ihrer Gruppe, "
        "aktion='alle_trennen' hebt jede bestehende Gruppe auf "
        "('mach die Gruppe wieder auf')."
    )
    parameters = vol.Schema(
        {
            vol.Required("aktion"): vol.In(["gruppieren", "trennen", "alle_trennen"]),
            vol.Optional("hauptplayer"): str,
            vol.Optional("player"): [str],
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        aktion: str = kwargs["aktion"]
        members: list[str] = kwargs.get("player") or []

        if aktion == "alle_trennen":
            return await self._async_ungroup_all()
        if aktion == "trennen":
            return await self._async_ungroup(members, llm_context)
        return await self._async_group(kwargs.get("hauptplayer"), members, llm_context)

    async def _async_group(
        self,
        leader_name: str | None,
        member_names: list[str],
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        runtime = self.runtime
        leader = resolve_player(runtime, leader_name, llm_context)
        members = [
            entity_id
            for entity_id in resolve_players(runtime, member_names)
            if entity_id != leader
        ]
        if not members:
            raise BardeError("Es fehlen die Lautsprecher, die dazukommen sollen")
        await async_media_player(runtime.hass, "join", leader, group_members=members)
        return {
            "gruppe": [label(runtime, entity_id) for entity_id in [leader, *members]],
            "leader": label(runtime, leader),
        }

    async def _async_ungroup(
        self, member_names: list[str], llm_context: llm.LLMContext
    ) -> dict[str, Any]:
        runtime = self.runtime
        if member_names:
            targets = resolve_players(runtime, member_names)
        else:
            targets = [resolve_player(runtime, None, llm_context)]
        for entity_id in targets:
            await async_media_player(runtime.hass, "unjoin", entity_id)
        return {"getrennt": [label(runtime, entity_id) for entity_id in targets]}

    async def _async_ungroup_all(self) -> dict[str, Any]:
        runtime = self.runtime
        grouped: list[str] = []
        for entity_id in ma_players(runtime):
            state = runtime.hass.states.get(entity_id)
            if state and state.attributes.get(ATTR_GROUP_MEMBERS):
                grouped.append(entity_id)
        if not grouped:
            return {"getrennt": [], "hinweis": "Es war keine Gruppe aktiv"}
        for entity_id in grouped:
            await async_media_player(runtime.hass, "unjoin", entity_id)
        return {"getrennt": [label(runtime, entity_id) for entity_id in grouped]}
