"""Tests for the persistence of the traceability counters."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    mock_restore_cache_with_extra_data,
)

from custom_components.fallback_sensors.const import (
    ATTR_FALLBACK_COUNT,
    ATTR_LAST_FALLBACK_TIME,
)

from .conftest import BACKUP, PRIMARY, TEST_ENTITY_ID

LAST_FALLBACK = "2026-09-01T10:30:00+00:00"


def _restore(hass: HomeAssistant, extra_data: dict) -> None:
    """Seed the restore cache for the fallback sensor."""
    mock_restore_cache_with_extra_data(
        hass,
        ((State(TEST_ENTITY_ID, "21.5"), extra_data),),
    )


async def test_counters_are_restored(hass: HomeAssistant, setup_entry) -> None:
    """The counters survive a restart instead of starting over at zero."""
    _restore(
        hass,
        {"fallback_count": 4, "last_fallback_time": LAST_FALLBACK},
    )
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes[ATTR_FALLBACK_COUNT] == 4
    assert state.attributes[ATTR_LAST_FALLBACK_TIME] == LAST_FALLBACK


async def test_restored_counters_keep_counting(
    hass: HomeAssistant, setup_entry
) -> None:
    """A fallback after a restart increments the restored value."""
    _restore(hass, {"fallback_count": 4, "last_fallback_time": LAST_FALLBACK})
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry()

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes[ATTR_FALLBACK_COUNT] == 5
    assert state.attributes[ATTR_LAST_FALLBACK_TIME] != LAST_FALLBACK
    assert dt_util.parse_datetime(state.attributes[ATTR_LAST_FALLBACK_TIME])


async def test_missing_restore_data_starts_from_zero(
    hass: HomeAssistant, setup_entry
) -> None:
    """A first run, with nothing stored, starts at zero."""
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes[ATTR_FALLBACK_COUNT] == 0
    assert state.attributes[ATTR_LAST_FALLBACK_TIME] is None


async def test_corrupted_restore_data_is_ignored(
    hass: HomeAssistant, setup_entry
) -> None:
    """Unusable stored data does not prevent the sensor from starting."""
    _restore(hass, {"fallback_count": "not a number"})
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "21.5"
    assert state.attributes[ATTR_FALLBACK_COUNT] == 0


async def test_restore_without_last_fallback_time(
    hass: HomeAssistant, setup_entry
) -> None:
    """A count restored without a timestamp is accepted."""
    _restore(hass, {"fallback_count": 2, "last_fallback_time": None})
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes[ATTR_FALLBACK_COUNT] == 2
    assert state.attributes[ATTR_LAST_FALLBACK_TIME] is None
