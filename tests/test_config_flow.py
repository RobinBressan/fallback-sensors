"""Tests for the Fallback Sensors config flow."""

from __future__ import annotations

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.fallback_sensors.const import (
    ATTR_CURRENT_SOURCE,
    CONF_ENTITIES,
    CONF_HYSTERESIS_DELAY,
    DOMAIN,
)

from .conftest import BACKUP, PRIMARY, TEST_ENTITY_ID, TEST_NAME

THIRD = "sensor.third"


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The user step creates a config entry from the submitted form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living Room",
            CONF_ENTITIES: [PRIMARY, BACKUP],
            CONF_HYSTERESIS_DELAY: 30,
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room"
    assert result["data"][CONF_ENTITIES] == [PRIMARY, BACKUP]
    assert result["data"][CONF_HYSTERESIS_DELAY] == 30


async def test_user_flow_requires_two_entities(hass: HomeAssistant) -> None:
    """A single source entity is rejected with a form error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Living Room", CONF_ENTITIES: [PRIMARY]},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {CONF_ENTITIES: "min_entities"}


async def test_user_flow_rejects_a_source_that_is_a_dependent_fallback_sensor(
    hass: HomeAssistant, setup_entry
) -> None:
    """A source chain that would loop back to the new sensor is refused."""
    hass.states.async_set(PRIMARY, "21.5")
    # An existing fallback sensor whose own source is the entity ID the new
    # sensor is about to get.
    await setup_entry(name="Existing", entities=[PRIMARY, "sensor.new_sensor"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "New Sensor", CONF_ENTITIES: ["sensor.existing", PRIMARY]},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {CONF_ENTITIES: "circular_reference"}


async def test_user_flow_rejects_self_reference(hass: HomeAssistant) -> None:
    """Selecting the entity ID the new sensor will get is refused."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Loop", CONF_ENTITIES: ["sensor.loop", PRIMARY]},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {CONF_ENTITIES: "self_reference"}


async def test_options_flow_updates_the_entry(hass: HomeAssistant, setup_entry) -> None:
    """The options flow can be opened and updates the entry in place."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    hass.states.async_set(THIRD, "18.0")
    entry = await setup_entry()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "name": "Renamed",
            CONF_ENTITIES: [THIRD, BACKUP],
            CONF_HYSTERESIS_DELAY: 12,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.title == "Renamed"
    assert entry.data[CONF_ENTITIES] == [THIRD, BACKUP]
    assert entry.data[CONF_HYSTERESIS_DELAY] == 12


async def test_options_flow_reloads_the_sensor(
    hass: HomeAssistant, setup_entry
) -> None:
    """Saving the options flow makes the sensor use the new source list."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    hass.states.async_set(THIRD, "18.0")
    entry = await setup_entry()

    assert hass.states.get(TEST_ENTITY_ID).state == "21.5"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": TEST_NAME, CONF_ENTITIES: [THIRD, BACKUP]},
    )
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "18.0"
    assert state.attributes[ATTR_CURRENT_SOURCE] == THIRD


async def test_options_flow_preserves_unexposed_keys(
    hass: HomeAssistant, setup_entry
) -> None:
    """Saving the options form keeps unique_id and conditions untouched."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    entry = await setup_entry(
        unique_id="my_unique_id",
        conditions=[{"type": "range", "min": 0, "max": 50}],
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": TEST_NAME, CONF_ENTITIES: [BACKUP, PRIMARY]},
    )
    await hass.async_block_till_done()

    assert entry.data["unique_id"] == "my_unique_id"
    assert entry.data["conditions"] == [{"type": "range", "min": 0, "max": 50}]


async def test_options_flow_rejects_self_reference(
    hass: HomeAssistant, setup_entry
) -> None:
    """The sensor's own entity ID cannot be added to its sources."""
    hass.states.async_set(PRIMARY, "21.5")
    entry = await setup_entry()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": TEST_NAME, CONF_ENTITIES: [TEST_ENTITY_ID, PRIMARY]},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {CONF_ENTITIES: "self_reference"}


async def test_options_flow_rejects_circular_reference(
    hass: HomeAssistant, setup_entry, build_entry
) -> None:
    """A source that already depends on this sensor is refused."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    entry = await setup_entry()

    other = build_entry(name="Other", entities=[TEST_ENTITY_ID, PRIMARY])
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": TEST_NAME, CONF_ENTITIES: ["sensor.other", PRIMARY]},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {CONF_ENTITIES: "circular_reference"}
