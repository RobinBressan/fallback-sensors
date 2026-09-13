"""Tests for the Fallback Sensors sensor platform."""

from __future__ import annotations

from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES, EntityComponent
from homeassistant.setup import async_setup_component

from custom_components.fallback_sensors.const import (
    ATTR_CURRENT_SOURCE,
    ATTR_SOURCE_ENTITIES,
    ATTR_SOURCE_INDEX,
)
from custom_components.fallback_sensors.loop_guard import async_get_source_registry

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


async def test_existing_entry_with_self_reference_drops_the_source(
    hass: HomeAssistant, setup_entry, integration_logs: list[str]
) -> None:
    """A stored configuration that references the sensor itself is neutralised."""
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry(entities=[TEST_ENTITY_ID, PRIMARY])

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "21.5"
    # The looping source is dropped, the remaining one still works.
    assert state.attributes[ATTR_SOURCE_ENTITIES] == [PRIMARY]
    assert any(
        "would make the sensor depend on its own state" in message
        for message in integration_logs
    )


async def test_existing_entry_with_circular_reference_drops_the_source(
    hass: HomeAssistant, setup_entry, build_entry
) -> None:
    """A source chain looping back to the sensor is neutralised."""
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry(name="Other", entities=[TEST_ENTITY_ID, PRIMARY])

    entry = build_entry(entities=["sensor.other", PRIMARY])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes[ATTR_SOURCE_ENTITIES] == [PRIMARY]


async def test_yaml_setup_refuses_a_self_referencing_configuration(
    hass: HomeAssistant, integration_logs: list[str]
) -> None:
    """A looping YAML configuration does not create a sensor at all."""
    hass.states.async_set(PRIMARY, "21.5")

    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "fallback_sensors",
                "name": "Yaml Loop",
                "entities": ["sensor.yaml_loop", PRIMARY],
            }
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.yaml_loop") is None
    assert any(
        "Refusing to set up fallback sensor" in message for message in integration_logs
    )


async def test_sources_are_unregistered_on_unload(
    hass: HomeAssistant, setup_entry
) -> None:
    """Unloading an entry removes it from the dependency registry."""
    hass.states.async_set(PRIMARY, "21.5")
    entry = await setup_entry()

    assert TEST_ENTITY_ID in async_get_source_registry(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert TEST_ENTITY_ID not in async_get_source_registry(hass)


async def test_own_state_event_is_ignored(
    hass: HomeAssistant, setup_entry, integration_logs: list[str]
) -> None:
    """A state event for the sensor itself never reaches the update logic."""
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry()

    component: EntityComponent = hass.data[DATA_INSTANCES]["sensor"]
    entity = component.get_entity(TEST_ENTITY_ID)
    assert entity is not None

    event = Event(
        EVENT_STATE_CHANGED,
        {
            "entity_id": TEST_ENTITY_ID,
            "old_state": None,
            "new_state": hass.states.get(TEST_ENTITY_ID),
        },
    )
    entity._handle_source_change(event)

    assert any(
        "received its own state change event and ignored it" in message
        for message in integration_logs
    )
