"""Tests for the hysteresis delay of Fallback Sensors."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.fallback_sensors.const import (
    ATTR_CURRENT_SOURCE,
    ATTR_FALLBACK_COUNT,
)

from .conftest import BACKUP, PRIMARY, TEST_ENTITY_ID

DELAY = 30


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int):
    """Advance time and let scheduled callbacks run."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_fallback_count_starts_at_zero(hass: HomeAssistant, setup_entry) -> None:
    """Picking the first source at startup is not a fallback."""
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.attributes[ATTR_CURRENT_SOURCE] == PRIMARY
    assert state.attributes[ATTR_FALLBACK_COUNT] == 0


async def test_switch_is_delayed_then_applied(
    hass: HomeAssistant, setup_entry, freezer: FrozenDateTimeFactory
) -> None:
    """The sensor keeps the failing source until the delay has elapsed."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry(hysteresis_delay=DELAY)

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "21.5"
    assert state.attributes[ATTR_CURRENT_SOURCE] == PRIMARY

    await _tick(hass, freezer, DELAY + 1)

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "19.0"
    assert state.attributes[ATTR_CURRENT_SOURCE] == BACKUP
    assert state.attributes[ATTR_FALLBACK_COUNT] == 1


async def test_switch_is_not_counted_twice(
    hass: HomeAssistant, setup_entry, freezer: FrozenDateTimeFactory
) -> None:
    """A source event past the delay does not apply the switch a second time.

    Regression test: the "delay elapsed" branch used to apply the switch
    without clearing the pending state nor cancelling the timer, so the timer
    applied it again and `fallback_count` was incremented twice for a single
    switch.
    """
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry(hysteresis_delay=DELAY)

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    # A source event arrives after the delay has elapsed but before the timer
    # has run.
    freezer.tick(timedelta(seconds=DELAY + 1))
    hass.states.async_set(BACKUP, "19.5")
    await hass.async_block_till_done()

    # ... and then the timer fires.
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "19.5"
    assert state.attributes[ATTR_CURRENT_SOURCE] == BACKUP
    assert state.attributes[ATTR_FALLBACK_COUNT] == 1

    # Further events on the active source do not count either.
    hass.states.async_set(BACKUP, "19.7")
    await hass.async_block_till_done()
    await _tick(hass, freezer, DELAY + 1)

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "19.7"
    assert state.attributes[ATTR_FALLBACK_COUNT] == 1


async def test_pending_switch_is_abandoned_when_the_source_recovers(
    hass: HomeAssistant, setup_entry, freezer: FrozenDateTimeFactory
) -> None:
    """A source recovering within the delay cancels the pending switch."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry(hysteresis_delay=DELAY)

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    await _tick(hass, freezer, DELAY // 3)
    hass.states.async_set(PRIMARY, "22.0")
    await hass.async_block_till_done()

    await _tick(hass, freezer, DELAY * 2)

    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "22.0"
    assert state.attributes[ATTR_CURRENT_SOURCE] == PRIMARY
    assert state.attributes[ATTR_FALLBACK_COUNT] == 0


async def test_pending_target_change_restarts_the_delay(
    hass: HomeAssistant, setup_entry, freezer: FrozenDateTimeFactory
) -> None:
    """Aiming at another source while waiting restarts the hysteresis delay."""
    third = "sensor.third"
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    hass.states.async_set(third, "18.0")
    await setup_entry(entities=[PRIMARY, BACKUP, third], hysteresis_delay=DELAY)

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    # Two thirds into the wait, the pending target itself becomes invalid.
    await _tick(hass, freezer, (DELAY * 2) // 3)
    hass.states.async_set(BACKUP, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    # The original deadline passes without a switch: the delay was restarted.
    await _tick(hass, freezer, DELAY // 2)
    assert hass.states.get(TEST_ENTITY_ID).state == "21.5"

    await _tick(hass, freezer, DELAY)
    state = hass.states.get(TEST_ENTITY_ID)
    assert state.state == "18.0"
    assert state.attributes[ATTR_CURRENT_SOURCE] == third
    assert state.attributes[ATTR_FALLBACK_COUNT] == 1


async def test_losing_every_source_is_delayed_and_applied(
    hass: HomeAssistant, setup_entry, freezer: FrozenDateTimeFactory
) -> None:
    """Going unavailable also waits for the delay, and does happen."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry(hysteresis_delay=DELAY)

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    hass.states.async_set(BACKUP, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    assert hass.states.get(TEST_ENTITY_ID).state == "21.5"

    # No further source event will ever arrive: only the timer can apply it.
    await _tick(hass, freezer, DELAY + 1)

    assert hass.states.get(TEST_ENTITY_ID).state == STATE_UNAVAILABLE


async def test_timer_is_cancelled_when_the_entity_is_removed(
    hass: HomeAssistant, setup_entry, freezer: FrozenDateTimeFactory
) -> None:
    """Unloading while a switch is pending leaves no timer and no listener."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    entry = await setup_entry(hysteresis_delay=DELAY)

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED

    # The pending timer must not fire on a removed entity, and the source
    # listener must be gone: neither changes the restored state.
    await _tick(hass, freezer, DELAY * 2)
    hass.states.async_set(BACKUP, "12.3")
    await hass.async_block_till_done()

    assert hass.states.get(TEST_ENTITY_ID).state == STATE_UNAVAILABLE


async def test_source_change_errors_are_swallowed(
    hass: HomeAssistant, setup_entry, integration_logs: list[str]
) -> None:
    """A failure while handling a source change never escapes the listener."""
    hass.states.async_set(PRIMARY, "21.5")
    await setup_entry()

    with patch(
        "custom_components.fallback_sensors.sensor.FallbackSensor._get_active_entity",
        side_effect=RuntimeError("boom"),
    ):
        hass.states.async_set(PRIMARY, "22.0")
        await hass.async_block_till_done()

    assert any(
        "Unexpected error while handling a source change" in message
        for message in integration_logs
    )


async def test_pending_switch_errors_are_swallowed(
    hass: HomeAssistant,
    setup_entry,
    freezer: FrozenDateTimeFactory,
    integration_logs: list[str],
) -> None:
    """A failure while applying a pending switch never escapes the timer."""
    hass.states.async_set(PRIMARY, "21.5")
    hass.states.async_set(BACKUP, "19.0")
    await setup_entry(hysteresis_delay=DELAY)

    hass.states.async_set(PRIMARY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    with patch(
        "custom_components.fallback_sensors.sensor.FallbackSensor._get_active_entity",
        side_effect=RuntimeError("boom"),
    ):
        await _tick(hass, freezer, DELAY + 1)

    assert any(
        "Unexpected error while applying the pending source" in message
        for message in integration_logs
    )
