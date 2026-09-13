"""Tests for editing conditions through the config and options flows."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
import voluptuous as vol

from custom_components.fallback_sensors.config_flow import (
    FORM_CONDITION_MAX,
    FORM_CONDITION_MIN,
    FORM_CONDITION_PATTERN,
)
from custom_components.fallback_sensors.const import (
    ATTR_CURRENT_SOURCE,
    CONF_CONDITIONS,
    CONF_ENTITIES,
    DOMAIN,
)

from .conftest import BACKUP, PRIMARY, TEST_ENTITY_ID, TEST_NAME

RANGE_CONDITION = {"type": "range", "min": -50.0, "max": 60.0}
REGEX_CONDITION = {"type": "regex", "pattern": r"^-?\d+(\.\d+)?$"}


def _suggested(schema: vol.Schema, key: str) -> Any:
    """Return the value the form pre-fills for `key`."""
    for marker in schema.schema:
        if marker == key:
            return (marker.description or {}).get("suggested_value")
    raise AssertionError(f"{key} is not in the form")


async def test_user_flow_stores_conditions(hass: HomeAssistant) -> None:
    """Range and regex conditions entered in the form are stored."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living Room",
            CONF_ENTITIES: [PRIMARY, BACKUP],
            FORM_CONDITION_MIN: -50,
            FORM_CONDITION_MAX: 60,
            FORM_CONDITION_PATTERN: r"^-?\d+(\.\d+)?$",
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONDITIONS] == [RANGE_CONDITION, REGEX_CONDITION]
    # Form-only keys are not stored.
    assert FORM_CONDITION_MIN not in result["data"]


async def test_user_flow_without_conditions_stores_an_empty_list(
    hass: HomeAssistant,
) -> None:
    """Leaving the condition fields empty stores no condition."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Living Room", CONF_ENTITIES: [PRIMARY, BACKUP]},
    )

    assert result["data"][CONF_CONDITIONS] == []


async def test_user_flow_accepts_a_single_bound(hass: HomeAssistant) -> None:
    """A range with only a minimum is valid."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living Room",
            CONF_ENTITIES: [PRIMARY, BACKUP],
            FORM_CONDITION_MIN: 0,
        },
    )

    assert result["data"][CONF_CONDITIONS] == [{"type": "range", "min": 0.0}]


async def test_user_flow_rejects_an_inverted_range(hass: HomeAssistant) -> None:
    """A minimum above the maximum is refused."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living Room",
            CONF_ENTITIES: [PRIMARY, BACKUP],
            FORM_CONDITION_MIN: 60,
            FORM_CONDITION_MAX: -50,
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {FORM_CONDITION_MIN: "invalid_range"}


async def test_user_flow_rejects_an_invalid_pattern(hass: HomeAssistant) -> None:
    """A pattern that does not compile is refused."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living Room",
            CONF_ENTITIES: [PRIMARY, BACKUP],
            FORM_CONDITION_PATTERN: "([unclosed",
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {FORM_CONDITION_PATTERN: "invalid_regex"}


async def test_options_flow_prefills_stored_conditions(
    hass: HomeAssistant, setup_entry
) -> None:
    """Stored conditions come back as form defaults."""
    hass.states.async_set(PRIMARY, "21.5")
    entry = await setup_entry(conditions=[RANGE_CONDITION, REGEX_CONDITION])

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"]

    assert _suggested(schema, FORM_CONDITION_MIN) == -50.0
    assert _suggested(schema, FORM_CONDITION_MAX) == 60.0
    assert _suggested(schema, FORM_CONDITION_PATTERN) == REGEX_CONDITION["pattern"]


async def test_options_flow_updates_conditions(
    hass: HomeAssistant, setup_entry
) -> None:
    """Editing the condition fields updates the stored list."""
    hass.states.async_set(PRIMARY, "150")
    hass.states.async_set(BACKUP, "19.0")
    entry = await setup_entry()

    assert hass.states.get(TEST_ENTITY_ID).attributes[ATTR_CURRENT_SOURCE] == PRIMARY

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "name": TEST_NAME,
            CONF_ENTITIES: [PRIMARY, BACKUP],
            FORM_CONDITION_MAX: 60,
        },
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_CONDITIONS] == [{"type": "range", "max": 60.0}]
    # The out of range primary source is now skipped.
    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes[ATTR_CURRENT_SOURCE] == BACKUP


async def test_options_flow_clears_conditions(hass: HomeAssistant, setup_entry) -> None:
    """Emptying the condition fields removes the conditions."""
    hass.states.async_set(PRIMARY, "150")
    hass.states.async_set(BACKUP, "19.0")
    entry = await setup_entry(conditions=[RANGE_CONDITION])

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": TEST_NAME, CONF_ENTITIES: [PRIMARY, BACKUP]},
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_CONDITIONS] == []
    assert hass.states.get(TEST_ENTITY_ID).attributes[ATTR_CURRENT_SOURCE] == PRIMARY
