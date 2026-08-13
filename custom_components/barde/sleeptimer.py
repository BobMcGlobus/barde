"""Sleep timers.

Music Assistant has no sleep timer — no action, no queue flag, no client
command — so Barde keeps its own, one per player.

Two details matter for something that runs while you fall asleep: it fades the
volume down instead of cutting the music off, and it puts the volume back
afterwards, so the next morning does not start in silence (or, worse, at the
volume of a fade that never finished). Timers live in memory only; a Home
Assistant restart clears them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    FADE_MIN_VOLUME,
    FADE_SECONDS,
    FADE_STEP_SECONDS,
)
from .exceptions import BardeError
from .ma import async_media_player

if TYPE_CHECKING:
    from .api import BardeRuntime

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _Timer:
    """One pending sleep timer."""

    ends_at: datetime
    unsub: CALLBACK_TYPE | None = None
    original_volume: float | None = None
    steps_total: int = 0
    steps_left: int = 0
    volume_step: float = 0.0


class SleepTimers:
    """Pending sleep timers, keyed by player entity id."""

    def __init__(self, runtime: BardeRuntime) -> None:
        """Bind the timers to their runtime."""
        self.runtime = runtime
        self._timers: dict[str, _Timer] = {}

    @callback
    def async_set(self, entity_id: str, minutes: int, fade: bool = True) -> datetime:
        """Arm (or re-arm) the timer for one player; returns when it ends."""
        self.async_cancel(entity_id)

        seconds = minutes * 60
        # Never spend more than half the timer fading — "aus in 2 Minuten"
        # should still play something.
        fade_seconds = min(FADE_SECONDS, seconds // 2) if fade else 0
        timer = _Timer(ends_at=dt_util.utcnow() + timedelta(seconds=seconds))
        self._timers[entity_id] = timer
        timer.unsub = async_call_later(
            self.runtime.hass,
            max(1, seconds - fade_seconds),
            self._make_handler(entity_id, timer, fade_seconds),
        )
        return timer.ends_at

    @callback
    def async_cancel(self, entity_id: str) -> bool:
        """Drop the timer; restores the volume when a fade was running."""
        timer = self._timers.pop(entity_id, None)
        if timer is None:
            return False
        if timer.unsub is not None:
            timer.unsub()
        if timer.original_volume is not None:
            self.runtime.hass.async_create_task(
                self._async_set_volume(entity_id, timer.original_volume)
            )
        return True

    @callback
    def async_cancel_all(self) -> None:
        """Drop every timer (entry unload)."""
        for entity_id in list(self._timers):
            self.async_cancel(entity_id)

    def remaining(self, entity_id: str) -> int | None:
        """Minutes left on this player's timer, rounded up."""
        timer = self._timers.get(entity_id)
        if timer is None:
            return None
        seconds = (timer.ends_at - dt_util.utcnow()).total_seconds()
        return max(0, -(-int(seconds) // 60))

    def active(self) -> dict[str, int]:
        """Remaining minutes for every player with a timer."""
        return {entity_id: self.remaining(entity_id) or 0 for entity_id in self._timers}

    def _make_handler(self, entity_id: str, timer: _Timer, fade_seconds: int):
        async def _fire(_now: datetime) -> None:
            timer.unsub = None
            if self._timers.get(entity_id) is not timer:
                return  # replaced or cancelled in the meantime
            if fade_seconds:
                await self._async_begin_fade(entity_id, timer, fade_seconds)
            else:
                await self._async_finish(entity_id, timer)

        return _fire

    async def _async_begin_fade(
        self, entity_id: str, timer: _Timer, fade_seconds: int
    ) -> None:
        """Start lowering the volume towards the end of the timer."""
        state = self.runtime.hass.states.get(entity_id)
        volume = state.attributes.get("volume_level") if state else None
        if volume is None:
            await self._async_finish(entity_id, timer)
            return

        timer.original_volume = float(volume)
        timer.steps_total = max(1, fade_seconds // FADE_STEP_SECONDS)
        timer.steps_left = timer.steps_total
        target = timer.original_volume * FADE_MIN_VOLUME
        timer.volume_step = (timer.original_volume - target) / timer.steps_total
        await self._async_fade_step(entity_id, timer)

    async def _async_fade_step(self, entity_id: str, timer: _Timer) -> None:
        """One notch quieter, then schedule the next notch.

        The ramp is computed from the volume we started with, not from what
        the player currently reports — a player that updates its state late
        would otherwise stall the fade.
        """
        if self._timers.get(entity_id) is not timer:
            return
        timer.steps_left -= 1
        if timer.steps_left <= 0 or timer.original_volume is None:
            await self._async_finish(entity_id, timer)
            return

        done = timer.steps_total - timer.steps_left
        await self._async_set_volume(
            entity_id, timer.original_volume - timer.volume_step * done
        )

        async def _next(_now: datetime) -> None:
            timer.unsub = None
            await self._async_fade_step(entity_id, timer)

        timer.unsub = async_call_later(self.runtime.hass, FADE_STEP_SECONDS, _next)

    async def _async_finish(self, entity_id: str, timer: _Timer) -> None:
        """Stop the music and hand the volume back."""
        self._timers.pop(entity_id, None)
        hass = self.runtime.hass
        try:
            await async_media_player(hass, "media_pause", entity_id)
        except BardeError as err:
            # Radio streams cannot always pause.
            _LOGGER.debug("Pause failed for %s, stopping instead: %s", entity_id, err)
            try:
                await async_media_player(hass, "media_stop", entity_id)
            except BardeError as stop_err:
                _LOGGER.warning(
                    "Sleep timer could not stop %s: %s", entity_id, stop_err
                )
        if timer.original_volume is not None:
            await self._async_set_volume(entity_id, timer.original_volume)

    async def _async_set_volume(self, entity_id: str, volume: float) -> None:
        try:
            await async_media_player(
                self.runtime.hass,
                "volume_set",
                entity_id,
                volume_level=round(min(1.0, max(0.0, volume)), 3),
            )
        except BardeError as err:
            _LOGGER.debug("Volume change failed for %s: %s", entity_id, err)
