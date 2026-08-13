"""Config flow for Barde — single instance, everything else is an option."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .const import (
    CONF_CONTEXT_TTL,
    CONF_DEFAULT_PLAYER,
    CONF_EXPOSE_FAVORITES,
    CONF_EXPOSE_PLAYLISTS,
    CONF_MA_ENTRY_ID,
    CONF_PROVIDER_PREFERENCE,
    CONF_RESPECT_EXPOSURE,
    CONF_VOLUME_STEP,
    DEFAULT_CONTEXT_TTL,
    DEFAULT_EXPOSE_FAVORITES,
    DEFAULT_EXPOSE_PLAYLISTS,
    DEFAULT_PROVIDER_PREFERENCE,
    DEFAULT_RESPECT_EXPOSURE,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
    KNOWN_PROVIDERS,
    MA_DOMAIN,
    MA_ENTRY_AUTO,
)

TITLE = "Barde"


class BardeConfigFlow(ConfigFlow, domain=DOMAIN):
    """One Barde per installation; Music Assistant must already be set up."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the single instance."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if not self.hass.config_entries.async_entries(MA_DOMAIN):
            return self.async_abort(reason="music_assistant_missing")
        if user_input is not None:
            return self.async_create_entry(title=TITLE, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> BardeOptionsFlow:
        """Return the options flow handler."""
        return BardeOptionsFlow()


class BardeOptionsFlow(OptionsFlow):
    """All tuning knobs live here — nothing needs a re-add."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(self.hass, current)
        )


def _options_schema(hass: HomeAssistant, current: dict[str, Any]) -> vol.Schema:
    """Build the options schema, pre-filled with the current values."""
    ma_options = [SelectOptionDict(value=MA_ENTRY_AUTO, label="Automatisch")]
    ma_options.extend(
        SelectOptionDict(value=entry.entry_id, label=entry.title)
        for entry in hass.config_entries.async_entries(MA_DOMAIN)
    )

    return vol.Schema(
        {
            vol.Optional(
                CONF_DEFAULT_PLAYER,
                description={"suggested_value": current.get(CONF_DEFAULT_PLAYER)},
            ): EntitySelector(
                EntitySelectorConfig(domain="media_player", integration=MA_DOMAIN)
            ),
            vol.Optional(
                CONF_EXPOSE_PLAYLISTS,
                default=current.get(CONF_EXPOSE_PLAYLISTS, DEFAULT_EXPOSE_PLAYLISTS),
            ): BooleanSelector(),
            vol.Optional(
                CONF_EXPOSE_FAVORITES,
                default=current.get(CONF_EXPOSE_FAVORITES, DEFAULT_EXPOSE_FAVORITES),
            ): BooleanSelector(),
            vol.Optional(
                CONF_CONTEXT_TTL,
                default=current.get(CONF_CONTEXT_TTL, DEFAULT_CONTEXT_TTL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=1440, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_VOLUME_STEP,
                default=current.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=50, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Optional(
                CONF_PROVIDER_PREFERENCE,
                default=current.get(
                    CONF_PROVIDER_PREFERENCE, DEFAULT_PROVIDER_PREFERENCE
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=KNOWN_PROVIDERS,
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_RESPECT_EXPOSURE,
                default=current.get(CONF_RESPECT_EXPOSURE, DEFAULT_RESPECT_EXPOSURE),
            ): BooleanSelector(),
            vol.Optional(
                CONF_MA_ENTRY_ID,
                default=current.get(CONF_MA_ENTRY_ID, MA_ENTRY_AUTO),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=ma_options, mode=SelectSelectorMode.DROPDOWN
                )
            ),
        }
    )
