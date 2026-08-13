"""einschlaftimer — stop the music after a while."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
from homeassistant.util import dt as dt_util
import voluptuous as vol

from ..const import DEFAULT_SLEEP_MINUTES, MAX_SLEEP_MINUTES
from ..resolver import label, resolve_player
from .base import BardeTool


class SleepTimerTool(BardeTool):
    """Set, cancel and query the sleep timer."""

    name = "einschlaftimer"
    description = (
        "Beendet die Wiedergabe nach einer Weile — die Lautstärke wird zum "
        "Schluss langsam heruntergefahren und danach wieder hergestellt. "
        "'stell den Einschlaftimer auf 30 Minuten' → aktion='setzen', "
        "minuten=30; 'mach in einer halben Stunde aus' → dasselbe; "
        "'wie lange läuft der Timer noch' → aktion='status'; "
        "'stopp den Einschlaftimer' → aktion='abbrechen'. Ohne minuten "
        f"werden {DEFAULT_SLEEP_MINUTES} Minuten genommen. ausblenden=false "
        "schaltet ohne Ausblenden hart ab."
    )
    parameters = vol.Schema(
        {
            vol.Optional("aktion", default="setzen"): vol.In(
                ["setzen", "abbrechen", "status"]
            ),
            vol.Optional("minuten"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=MAX_SLEEP_MINUTES)
            ),
            vol.Optional("player"): str,
            vol.Optional("ausblenden", default=True): bool,
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        aktion: str = kwargs.get("aktion", "setzen")

        if aktion == "status" and not kwargs.get("player"):
            return self._all_timers()

        entity_id = resolve_player(
            runtime, kwargs.get("player"), llm_context, prefer_playing=True
        )
        name = label(runtime, entity_id)

        if aktion == "abbrechen":
            return {
                "aktion": "abbrechen",
                "player": name,
                "abgebrochen": runtime.timers.async_cancel(entity_id),
            }

        if aktion == "status":
            remaining = runtime.timers.remaining(entity_id)
            return {
                "aktion": "status",
                "player": name,
                "verbleibend_min": remaining,
                "aktiv": remaining is not None,
            }

        minutes: int = kwargs.get("minuten") or DEFAULT_SLEEP_MINUTES
        fade: bool = kwargs.get("ausblenden", True)
        ends_at = runtime.timers.async_set(entity_id, minutes, fade)
        return {
            "aktion": "setzen",
            "player": name,
            "minuten": minutes,
            "endet_um": dt_util.as_local(ends_at).strftime("%H:%M"),
            "ausblenden": fade,
        }

    def _all_timers(self) -> dict[str, Any]:
        """Every running timer — "läuft noch irgendwo ein Timer?"."""
        runtime = self.runtime
        active = runtime.timers.active()
        return {
            "aktion": "status",
            "timer": [
                {"player": label(runtime, entity_id), "verbleibend_min": minutes}
                for entity_id, minutes in active.items()
            ],
            "aktiv": bool(active),
        }
