"""Config flow for Fallback Sensors integration."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    CONDITION_TYPE_RANGE,
    CONDITION_TYPE_REGEX,
    CONF_CONDITION_MAX,
    CONF_CONDITION_MIN,
    CONF_CONDITION_PATTERN,
    CONF_CONDITION_TYPE,
    CONF_CONDITIONS,
    CONF_ENTITIES,
    CONF_HYSTERESIS_DELAY,
    DEFAULT_HYSTERESIS_DELAY,
    DEFAULT_NAME,
    DOMAIN,
)
from .loop_guard import async_find_loop, async_resolve_entity_id

_LOGGER = logging.getLogger(__name__)

MIN_ENTITIES = 2

# Form-only keys. Conditions are stored as the list the YAML platform uses;
# the form exposes the two shapes that list can take.
FORM_CONDITION_MIN = "condition_min"
FORM_CONDITION_MAX = "condition_max"
FORM_CONDITION_PATTERN = "condition_pattern"
FORM_ONLY_KEYS = (FORM_CONDITION_MIN, FORM_CONDITION_MAX, FORM_CONDITION_PATTERN)


def _conditions_to_form(conditions: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Flatten a stored condition list into form values.

    Args:
        conditions: Conditions stored on the config entry.

    Returns:
        Mapping of form key to current value.
    """
    values: dict[str, Any] = {}

    for condition in conditions or []:
        condition_type = condition.get(CONF_CONDITION_TYPE)

        if condition_type == CONDITION_TYPE_RANGE:
            if (minimum := condition.get(CONF_CONDITION_MIN)) is not None:
                values[FORM_CONDITION_MIN] = minimum
            if (maximum := condition.get(CONF_CONDITION_MAX)) is not None:
                values[FORM_CONDITION_MAX] = maximum
        elif condition_type == CONDITION_TYPE_REGEX and (
            pattern := condition.get(CONF_CONDITION_PATTERN)
        ):
            values[FORM_CONDITION_PATTERN] = pattern

    return values


def _form_to_conditions(user_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the stored condition list from form values.

    Args:
        user_input: Submitted form values.

    Returns:
        Condition list in the format the sensor platform consumes.
    """
    conditions: list[dict[str, Any]] = []

    minimum = user_input.get(FORM_CONDITION_MIN)
    maximum = user_input.get(FORM_CONDITION_MAX)
    if minimum is not None or maximum is not None:
        condition: dict[str, Any] = {CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE}
        if minimum is not None:
            condition[CONF_CONDITION_MIN] = minimum
        if maximum is not None:
            condition[CONF_CONDITION_MAX] = maximum
        conditions.append(condition)

    if pattern := (user_input.get(FORM_CONDITION_PATTERN) or "").strip():
        conditions.append(
            {
                CONF_CONDITION_TYPE: CONDITION_TYPE_REGEX,
                CONF_CONDITION_PATTERN: pattern,
            }
        )

    return conditions


def _build_entry_data(
    user_input: dict[str, Any], base: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Turn form values into the data stored on the config entry.

    Args:
        user_input: Submitted form values.
        base: Existing entry data to preserve, if any.

    Returns:
        Data dictionary to store on the config entry.
    """
    data = {**(base or {}), **user_input}
    for key in FORM_ONLY_KEYS:
        data.pop(key, None)

    data[CONF_CONDITIONS] = _form_to_conditions(user_input)
    return data


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

    minimum = user_input.get(FORM_CONDITION_MIN)
    maximum = user_input.get(FORM_CONDITION_MAX)
    if minimum is not None and maximum is not None and minimum > maximum:
        return {FORM_CONDITION_MIN: "invalid_range"}

    if pattern := (user_input.get(FORM_CONDITION_PATTERN) or "").strip():
        try:
            re.compile(pattern)
        except re.error:
            return {FORM_CONDITION_PATTERN: "invalid_regex"}

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

    # Conditions are optional and have no default: leaving a field empty
    # removes the corresponding condition.
    number_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            mode=selector.NumberSelectorMode.BOX,
            step="any",
        ),
    )
    for key, field_selector in (
        (FORM_CONDITION_MIN, number_selector),
        (FORM_CONDITION_MAX, number_selector),
        (FORM_CONDITION_PATTERN, selector.TextSelector()),
    ):
        schema[
            vol.Optional(key, description={"suggested_value": defaults.get(key)})
        ] = field_selector

    return vol.Schema(schema)


class FallbackSensorsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fallback Sensors."""

    VERSION = 2

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
                    data=_build_entry_data(user_input),
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
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=user_input[CONF_NAME],
                    data=_build_entry_data(user_input, self.config_entry.data),
                )
                return self.async_create_entry(title="", data={})

        if user_input is not None:
            defaults = dict(user_input)
        else:
            defaults = dict(self.config_entry.data)
            defaults.update(_conditions_to_form(defaults.get(CONF_CONDITIONS)))

        return self.async_show_form(
            step_id="init",
            data_schema=_async_build_schema(defaults, include_unique_id=False),
            errors=errors,
        )
