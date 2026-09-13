"""Tests for the Fallback Sensors sensor platform."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.fallback_sensors.const import (
    ATTR_CURRENT_SOURCE,
    ATTR_SOURCE_ENTITIES,
    ATTR_SOURCE_INDEX,
)

from .conftest import BACKUP, PRIMARY, TEST_ENTITY_ID

THIRD = "sensor.third"


async def test_uses_first_available_source(hass: HomeAssistant, setup_entry) -> None:
    """The first source of the ordered list wins when it is valid."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "21.5"
    assert state.attributes[ATTR_CURRENT_SOURCE] == PRIMARY
    assert state.attributes[ATTR_SOURCE_INDEX] == 0
    assert state.attributes[ATTR_SOURCE_ENTITIES] == [PRIMARY, BACKUP]


async def test_falls_back_when_primary_unavailable(
    hass: HomeAssistant, setup_entry
) -> None:
    """The sensor switches to the backup when the primary goes unavailable."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry()

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "19.0"
    assert state.attributes[ATTR_CURRENT_SOURCE] == BACKUP
    assert state.attributes[ATTR_SOURCE_INDEX] == 1


async def test_returns_to_primary_when_it_recovers(
    hass: HomeAssistant, setup_entry
) -> None:
    """The sensor goes back to the primary source as soon as it is valid again."""
    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry()

    assert hass.states.get(TEST_ENTITY_ID).state == "19.0"

    hass.states.async_set(PRIMARY, "21.5")
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "21.5"
    assert state.attributes[ATTR_CURRENT_SOURCE] == PRIMARY


async def test_unknown_and_missing_sources_are_skipped(
    hass: HomeAssistant, setup_entry
) -> None:
    """States `unknown`, `unavailable` and the literal `None` are not valid."""
    hass.states.async_set(PRIMARY, STATE_UNKNOWN)
    hass.states.async_set(BACKUP, "None")
    await setup_entry(entities=[PRIMARY, BACKUP, THIRD])

    assert hass.states.get(TEST_ENTITY_ID).state == STATE_UNAVAILABLE

    hass.states.async_set(THIRD, "7")
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "7"
    assert state.attributes[ATTR_SOURCE_INDEX] == 2


async def test_unavailable_when_no_source_is_valid(
    hass: HomeAssistant, setup_entry
) -> None:
    """Losing every source makes the fallback sensor unavailable."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry()

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    hass.states.async_set(BACKUP, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == STATE_UNAVAILABLE
    # Home Assistant drops extra state attributes while an entity is
    # unavailable, so traceability attributes are only exposed when a source
    # is active.
    assert ATTR_CURRENT_SOURCE not in state.attributes


async def test_attributes_follow_the_active_source(
    hass: HomeAssistant, setup_entry
) -> None:
    """Unit, device class and icon are taken from the active source."""
    hass.states.async_set(
        PRIMARY,
        "21.5",
        {
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "icon": "mdi:primary",
        },
    )
    hass.states.async_set(
        BACKUP,
        "68.0",
        {
            "unit_of_measurement": "°F",
            "device_class": "temperature",
            "icon": "mdi:backup",
        },
    )
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["icon"] == "mdi:primary"

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes["unit_of_measurement"] == "°F"
    assert state.attributes["icon"] == "mdi:backup"


async def test_range_condition_rejects_out_of_range_source(
    hass: HomeAssistant, setup_entry
) -> None:
    """A source outside the configured range is treated as invalid."""
    hass.states.async_set(PRIMARY, "150")
    hass.states.async_set(BACKUP, "20")
    await setup_entry(conditions=[{"type": "range", "min": -50, "max": 60}])

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "20"
    assert state.attributes[ATTR_CURRENT_SOURCE] == BACKUP


async def test_regex_condition_rejects_non_matching_source(
    hass: HomeAssistant, setup_entry
) -> None:
    """A source not matching the configured pattern is treated as invalid."""
    hass.states.async_set(PRIMARY, "error")
    hass.states.async_set(BACKUP, "20.5")
    await setup_entry(conditions=[{"type": "regex", "pattern": r"^-?\d+(\.\d+)?$"}])

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "20.5"
    assert state.attributes[ATTR_CURRENT_SOURCE] == BACKUP


async def test_yaml_setup(hass: HomeAssistant) -> None:
    """The platform can still be configured through YAML."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")

    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "fallback_sensors",
                "name": "Yaml Fallback",
                "unique_id": "yaml_fallback",
                "entities": [PRIMARY, BACKUP],
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.yaml_fallback")
    assert state is not None
    assert state.state == "21.5"
