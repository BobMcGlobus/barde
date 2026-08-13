"""The Barde integration — Music Assistant tools for Assist."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import llm

from .api import BardeAPI, BardeRuntime
from .const import CONF_MA_ENTRY_ID, MA_DOMAIN, MA_ENTRY_AUTO

_LOGGER = logging.getLogger(__name__)

type BardeConfigEntry = ConfigEntry[BardeRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: BardeConfigEntry) -> bool:
    """Set up Barde and register its LLM API."""
    ma_entry_id = _async_ma_entry_id(hass, entry)
    runtime = BardeRuntime(hass, entry, ma_entry_id)
    entry.runtime_data = runtime

    # Unregistering on unload is what makes a reload (options change) work.
    entry.async_on_unload(llm.async_register_api(hass, BardeAPI(hass, runtime)))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(runtime.timers.async_cancel_all)

    _LOGGER.debug("Barde registered against Music Assistant entry %s", ma_entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BardeConfigEntry) -> bool:
    """Unload the config entry."""
    return True


async def _async_update_listener(hass: HomeAssistant, entry: BardeConfigEntry) -> None:
    """Reload on option changes so the new prompt takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_ma_entry_id(hass: HomeAssistant, entry: BardeConfigEntry) -> str:
    """Find the Music Assistant config entry the actions should target."""
    entries = hass.config_entries.async_entries(MA_DOMAIN)
    configured = entry.options.get(CONF_MA_ENTRY_ID) or entry.data.get(CONF_MA_ENTRY_ID)

    if configured and configured != MA_ENTRY_AUTO:
        for candidate in entries:
            if candidate.entry_id != configured:
                continue
            if candidate.state is not ConfigEntryState.LOADED:
                raise ConfigEntryNotReady(
                    "Die gewählte Music-Assistant-Instanz ist nicht geladen"
                )
            return configured
        raise ConfigEntryError(
            "Die in den Optionen gewählte Music-Assistant-Instanz existiert nicht mehr"
        )

    loaded = [
        candidate for candidate in entries if candidate.state is ConfigEntryState.LOADED
    ]
    if not loaded:
        raise ConfigEntryNotReady(
            "Music Assistant ist nicht eingerichtet oder noch nicht geladen"
        )
    if len(loaded) > 1:
        raise ConfigEntryError(
            "Es gibt mehrere Music-Assistant-Instanzen — bitte in den "
            "Barde-Optionen eine auswählen"
        )
    return loaded[0].entry_id
