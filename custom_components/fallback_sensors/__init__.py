"""The Fallback Sensors integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Fallback Sensors component.

    Args:
        hass: Home Assistant instance.
        config: Configuration dictionary.

    Returns:
        True if setup was successful.
    """
    _LOGGER.debug("Setting up Fallback Sensors integration")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fallback Sensors from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry instance.

    Returns:
        True if setup was successful.
    """
    _LOGGER.debug("Setting up Fallback Sensors config entry: %s", entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Only add update listener on first setup, not on reload
    # The listener persists through reloads
    if not entry.update_listeners:
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry instance.

    Returns:
        True if unload was successful.
    """
    _LOGGER.debug("Unloading Fallback Sensors config entry: %s", entry.entry_id)

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry instance.
    """
    _LOGGER.debug("Reloading Fallback Sensors config entry: %s", entry.entry_id)

    if not await async_unload_entry(hass, entry):
        return

    await async_setup_entry(hass, entry)
