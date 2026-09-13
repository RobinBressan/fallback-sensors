"""Tests for state class handling and native value typing."""

from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES, EntityComponent

from .conftest import BACKUP, PRIMARY, TEST_ENTITY_ID

MEASUREMENT_ATTRS = {
    "unit_of_measurement": "°C",
    "device_class": "temperature",
    "state_class": SensorStateClass.MEASUREMENT,
}
TOTAL_ATTRS = {
    "unit_of_measurement": "kWh",
    "device_class": "energy",
    "state_class": SensorStateClass.TOTAL_INCREASING,
}


def _native_value(hass: HomeAssistant):
    """Return the native value object held by the fallback sensor."""
    component: EntityComponent = hass.data[DATA_INSTANCES]["sensor"]
    entity = component.get_entity(TEST_ENTITY_ID)
    assert entity is not None
    return entity.native_value


async def test_measurement_state_class_is_propagated(
    hass: HomeAssistant, setup_entry
) -> None:
    """A `measurement` source keeps its state class on the fallback sensor."""
    hass.states.async_set(PRIMARY, "21.5", MEASUREMENT_ATTRS)
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


async def test_total_increasing_state_class_is_not_propagated(
    hass: HomeAssistant, setup_entry
) -> None:
    """Cumulative state classes are dropped: switching counters breaks stats."""
    hass.states.async_set(PRIMARY, "1234.5", TOTAL_ATTRS)
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert "state_class" not in state.attributes
    # The rest of the source attributes still follow.
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert state.attributes["device_class"] == "energy"


async def test_total_state_class_is_not_propagated(
    hass: HomeAssistant, setup_entry
) -> None:
    """`total` is cumulative too and is dropped as well."""
    hass.states.async_set(
        PRIMARY, "42", {**TOTAL_ATTRS, "state_class": SensorStateClass.TOTAL}
    )
    await setup_entry()

    assert "state_class" not in hass.states.get(TEST_ENTITY_ID).attributes


async def test_state_class_follows_the_active_source(
    hass: HomeAssistant, setup_entry
) -> None:
    """The state class is re-evaluated on every switch."""
    hass.states.async_set(PRIMARY, "1234.5", TOTAL_ATTRS)
    hass.states.async_set(BACKUP, "21.5", MEASUREMENT_ATTRS)
    await setup_entry()

    assert "state_class" not in hass.states.get(TEST_ENTITY_ID).attributes

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


async def test_numeric_source_exposes_a_numeric_native_value(
    hass: HomeAssistant, setup_entry
) -> None:
    """A numeric sensor exposes a float, as Home Assistant expects."""
    hass.states.async_set(PRIMARY, "21.5", MEASUREMENT_ATTRS)
    await setup_entry()

    assert _native_value(hass) == 21.5
    assert isinstance(_native_value(hass), float)
    assert hass.states.get(TEST_ENTITY_ID).state == "21.5"


async def test_integer_source_keeps_its_rendering(
    hass: HomeAssistant, setup_entry
) -> None:
    """An integer state stays an integer, so the rendered state is unchanged."""
    hass.states.async_set(PRIMARY, "7", MEASUREMENT_ATTRS)
    await setup_entry()

    assert _native_value(hass) == 7
    assert isinstance(_native_value(hass), int)
    assert hass.states.get(TEST_ENTITY_ID).state == "7"


async def test_non_numeric_source_keeps_its_string_value(
    hass: HomeAssistant, setup_entry
) -> None:
    """A sensor with no numeric context is left as a string."""
    hass.states.async_set(PRIMARY, "007")
    await setup_entry()

    assert _native_value(hass) == "007"
    assert hass.states.get(TEST_ENTITY_ID).state == "007"


async def test_enum_source_keeps_its_string_value(
    hass: HomeAssistant, setup_entry
) -> None:
    """An explicitly non numeric device class is never converted."""
    hass.states.async_set(
        PRIMARY, "3", {"device_class": "enum", "options": ["1", "2", "3"]}
    )
    await setup_entry()

    assert _native_value(hass) == "3"


async def test_numeric_sensor_with_a_non_numeric_state_is_left_alone(
    hass: HomeAssistant, setup_entry
) -> None:
    """A value that cannot be converted is kept rather than dropped."""
    hass.states.async_set(PRIMARY, "n/a", {"unit_of_measurement": "°C"})
    await setup_entry()

    assert _native_value(hass) == "n/a"


async def test_infinite_value_is_not_converted(
    hass: HomeAssistant, setup_entry
) -> None:
    """`inf` parses as a float but would corrupt statistics, so it is kept."""
    hass.states.async_set(PRIMARY, "inf", MEASUREMENT_ATTRS)
    await setup_entry()

    assert _native_value(hass) == "inf"
