"""musik_uebernehmen — move the queue to another room."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm
import voluptuous as vol

from ..exceptions import BardeError
from ..resolver import label, resolve_player
from .base import BardeTool


class TransferTool(BardeTool):
    """Take the music with you."""

    name = "musik_uebernehmen"
    description = (
        "Übernimmt die laufende Wiedergabe inklusive Warteschlange auf einen "
        "anderen Lautsprecher: 'nimm das mit in die Küche' → nach='Küche'. "
        "von nur angeben, wenn der Nutzer die Quelle ausdrücklich nennt — "
        "sonst wird der Lautsprecher genommen, der gerade spielt. "
        "auto_play=false übernimmt die Warteschlange, ohne sie zu starten."
    )
    parameters = vol.Schema(
        {
            vol.Required("nach"): str,
            vol.Optional("von"): str,
            vol.Optional("auto_play", default=True): bool,
        }
    )

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        target = resolve_player(runtime, kwargs["nach"], llm_context)
        source = resolve_player(
            runtime, kwargs.get("von"), llm_context, prefer_playing=True
        )
        if source == target:
            raise BardeError(
                f"{label(runtime, target)} spielt bereits — kein Wechsel nötig"
            )
        auto_play = kwargs.get("auto_play", True)
        await runtime.ma.transfer_queue(
            target, source_player=source, auto_play=auto_play
        )
        return {
            "nach": label(runtime, target),
            "von": label(runtime, source),
            "läuft": auto_play,
        }
