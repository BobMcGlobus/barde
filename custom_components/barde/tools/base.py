"""Shared base class for the Barde tools."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
import voluptuous as vol

from ..exceptions import BardeError, PlayerNotFound

if TYPE_CHECKING:
    from ..api import BardeRuntime

_LOGGER = logging.getLogger(__name__)


class BardeTool(llm.Tool):
    """Validates arguments and turns failures into a payload the LLM can use."""

    def __init__(self, runtime: BardeRuntime) -> None:
        """Bind the tool to the runtime it operates on."""
        self.runtime = runtime
        self._validator: vol.Schema | None = None

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        """Run the tool; never raise into the conversation agent.

        The conversation chat log only recovers from ``HomeAssistantError`` and
        ``vol.Invalid`` — anything else aborts the whole Assist run with
        "Unexpected error during intent recognition". Music Assistant's own
        actions are not fully wrapped either (``handle_search`` lets
        ``MusicAssistantError`` through), so everything is caught here and
        handed to the model as a result it can talk about.
        """
        try:
            args = self._validate(tool_input.tool_args)
        except vol.Invalid as err:
            return {"fehler": f"Ungültige Parameter: {err}"}

        try:
            return await self._run(llm_context, **args)
        except PlayerNotFound as err:
            payload: dict[str, Any] = {"fehler": str(err)}
            if err.available:
                payload["verfügbar"] = err.available
            return payload
        except BardeError as err:
            return {"fehler": str(err)}
        except HomeAssistantError as err:
            _LOGGER.debug("%s failed: %s", self.name, err)
            return {"fehler": str(err)}
        except Exception as err:  # noqa: BLE001 - see docstring
            _LOGGER.exception("%s raised unexpectedly for args %s", self.name, args)
            return {"fehler": f"Interner Fehler ({type(err).__name__}): {err}"}

    def _validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Apply defaults and drop what the model made up.

        Models like to send empty strings for optional arguments; those would
        resolve to "the player called ''" further down.
        """
        if self._validator is None:
            self._validator = self.parameters.extend({}, extra=vol.REMOVE_EXTRA)
        cleaned = {
            key: value
            for key, value in raw.items()
            if not (isinstance(value, str) and not value.strip())
        }
        return self._validator(cleaned)

    async def _run(self, llm_context: llm.LLMContext, **kwargs: Any) -> dict[str, Any]:
        """Tool implementation."""
        raise NotImplementedError
