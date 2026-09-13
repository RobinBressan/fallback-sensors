"""Config flow for Fallback Sensors integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    CONF_ENTITIES,
    CONF_HYSTERESIS_DELAY,
    DEFAULT_HYSTERESIS_DELAY,
    DEFAULT_NAME,
    DOMAIN,
)
from .loop_guard import async_find_loop, async_resolve_entity_id

_LOGGER = logging.getLogger(__name__)

MIN_ENTITIES = 2


@callback
def _async_validate_input(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    entry: config_entries.ConfigEntry | None = None,
) -> dict[str, str]:
    """Validate the entities submitted through a flow.

    Args:
        hass: Home Assistant instance.
        user_input: Submitted form values.
        entry: Config entry being edited, if any.

    Returns:
        Mapping of field name to error key, empty when the input is valid.
    """
    entities: list[str] = user_input.get(CONF_ENTITIES, [])

    if len(entities) < MIN_ENTITIES:
        return {CONF_ENTITIES: "min_entities"}

    own_entity_id = async_resolve_entity_id(
        hass, user_input.get(CONF_NAME, DEFAULT_NAME), entry
    )
    if error := async_find_loop(hass, own_entity_id, entities):
        return {CONF_ENTITIES: error}

    return {}


def _async_build_schema(
    defaults: dict[str, Any], *, include_unique_id: bool
) -> vol.Schema:
    """Build the form schema shared by the config and options flows.

    Args:
        defaults: Current values used as form defaults.
        include_unique_id: Whether to offer the unique ID field.

    Returns:
        Voluptuous schema for the form.
    """
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)
        ): cv.string,
        vol.Required(
            CONF_ENTITIES, default=defaults.get(CONF_ENTITIES, [])
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                multiple=True,
            ),
        ),
    }

    if include_unique_id:
        schema[vol.Optional(CONF_UNIQUE_ID)] = cv.string

    schema[
        vol.Optional(
            CONF_HYSTERESIS_DELAY,
            default=defaults.get(CONF_HYSTERESIS_DELAY, DEFAULT_HYSTERESIS_DELAY),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=300,
            unit_of_measurement="seconds",
            mode=selector.NumberSelectorMode.BOX,
        ),
    )

    return vol.Schema(schema)


class FallbackSensorsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fallback Sensors."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step.

        Args:
            user_input: User input dictionary.

        Returns:
            Config flow result.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _async_validate_input(self.hass, user_input)
            if not errors:
                # Check for duplicate configuration
                await self.async_set_unique_id(user_input.get(CONF_UNIQUE_ID))
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_async_build_schema(user_input or {}, include_unique_id=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FallbackSensorsOptionsFlow:
        """Get the options flow for this handler.

        Args:
            config_entry: Config entry instance, provided by Home Assistant and
                exposed to the flow through `OptionsFlow.config_entry`.

        Returns:
            Options flow instance.
        """
        return FallbackSensorsOptionsFlow()


class FallbackSensorsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Fallback Sensors.

    The config entry is provided by the base class through the read-only
    `config_entry` property; assigning to it raises `AttributeError` since
    Home Assistant 2025.12.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options.

        Args:
            user_input: User input dictionary.

        Returns:
            Config flow result.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _async_validate_input(self.hass, user_input, self.config_entry)
            if not errors:
                # Preserve the keys the options form does not expose.
                data = {**self.config_entry.data, **user_input}
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=user_input[CONF_NAME],
                    data=data,
                )
                return self.async_create_entry(title="", data={})

        defaults = (
            user_input if user_input is not None else dict(self.config_entry.data)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=_async_build_schema(defaults, include_unique_id=False),
            errors=errors,
        )
