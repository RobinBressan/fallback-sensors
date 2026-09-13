"""Tests for the Fallback Sensors integration setup."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.fallback_sensors import CURRENT_VERSION
from custom_components.fallback_sensors.const import CONF_CONDITIONS

from .conftest import BACKUP, PRIMARY, TEST_ENTITY_ID


async def test_setup_and_unload_entry(hass: HomeAssistant, setup_entry) -> None:
    """A config entry sets up its sensor and removes it again on unload."""
    hass.states.async_set(PRIMARY, "21.5")
    entry = await setup_entry()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(TEST_ENTITY_ID) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    # The entity keeps a registry entry (it has a unique_id) but is restored
    # as unavailable once the platform is gone.
    state = hass.states.get(TEST_ENTITY_ID)
    assert state is not None
    assert state.state == "unavailable"
    assert state.attributes.get("restored") is True


async def test_reload_entry(hass: HomeAssistant, setup_entry) -> None:
    """Reloading a config entry keeps the sensor available."""
    hass.states.async_set(PRIMARY, "21.5")
    entry = await setup_entry()

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(TEST_ENTITY_ID)
    assert state is not None
    assert state.state == "21.5"


async def test_entry_without_sources_is_unavailable(
    hass: HomeAssistant, setup_entry
) -> None:
    """A sensor whose sources do not exist yet is unavailable."""
    await setup_entry(entities=[PRIMARY, BACKUP])

    state = hass.states.get(TEST_ENTITY_ID)
    assert state is not None
    assert state.state == "unavailable"


async def test_version_1_entry_is_migrated(hass: HomeAssistant, build_entry) -> None:
    """A version 1 entry gains the conditions key and loads normally."""
    hass.states.async_set(PRIMARY, "21.5")
    entry = build_entry(version=1)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == CURRENT_VERSION
    assert entry.data[CONF_CONDITIONS] == []
    assert hass.states.get(TEST_ENTITY_ID).state == "21.5"


async def test_migration_preserves_existing_data(
    hass: HomeAssistant, build_entry
) -> None:
    """Migrating never rewrites the keys an entry already has."""
    hass.states.async_set(PRIMARY, "21.5")
    conditions = [{"type": "range", "min": 0}]
    entry = build_entry(
        unique_id="kept", conditions=conditions, hysteresis_delay=5, version=1
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data["unique_id"] == "kept"
    assert entry.data[CONF_CONDITIONS] == conditions
    assert entry.data["hysteresis_delay"] == 5


async def test_entry_from_a_newer_version_is_not_loaded(
    hass: HomeAssistant, build_entry
) -> None:
    """An entry written by a newer integration is refused, not corrupted."""
    entry = build_entry(version=CURRENT_VERSION + 1)
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
