"""Barde specific errors.

All of these are caught by the tool base class and turned into a small
``{"fehler": ...}`` payload — the model should be able to react to a failure
instead of receiving a stack trace.
"""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class BardeError(HomeAssistantError):
    """Base class for recoverable Barde failures."""


class PlayerNotFound(BardeError):
    """No player could be resolved for the request."""

    def __init__(self, message: str, available: list[str] | None = None) -> None:
        """Carry the list of players the LLM may offer instead."""
        super().__init__(message)
        self.available = available or []


class NothingFound(BardeError):
    """A search returned no usable candidate."""
