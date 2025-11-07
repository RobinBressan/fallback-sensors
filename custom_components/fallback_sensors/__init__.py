"""The Fallback Sensors integration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
