"""Config flow for Fallback Sensors integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import CONF_ENTITIES, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FallbackSensorsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fallback Sensors."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step.

        Args:
            user_input: User input dictionary.

        Returns:
            Config flow result.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate entities list
            entities = user_input.get(CONF_ENTITIES, [])
            if len(entities) < 2:
                errors[CONF_ENTITIES] = "min_entities"
            else:
                # Check for duplicate configuration
                await self.async_set_unique_id(user_input.get(CONF_UNIQUE_ID))
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        # Show configuration form
        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Required(CONF_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        multiple=True,
                    ),
                ),
                vol.Optional(CONF_UNIQUE_ID): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FallbackSensorsOptionsFlow:
        """Get the options flow for this handler.

        Args:
            config_entry: Config entry instance.

        Returns:
            Options flow instance.
        """
        return FallbackSensorsOptionsFlow(config_entry)


class FallbackSensorsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Fallback Sensors."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow.

        Args:
            config_entry: Config entry instance.
        """
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage the options.

        Args:
            user_input: User input dictionary.

        Returns:
            Config flow result.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate entities list
            entities = user_input.get(CONF_ENTITIES, [])
            if len(entities) < 2:
                errors[CONF_ENTITIES] = "min_entities"
            else:
                return self.async_create_entry(title="", data=user_input)

        # Get current configuration
        current_name = self.config_entry.data.get(CONF_NAME, DEFAULT_NAME)
        current_entities = self.config_entry.data.get(CONF_ENTITIES, [])

        # Show options form
        options_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current_name): cv.string,
                vol.Required(
                    CONF_ENTITIES, default=current_entities
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        multiple=True,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )
