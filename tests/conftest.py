"""Pytest configuration and fixtures for Fallback Sensors tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass() -> HomeAssistant:
    """Create a mock Home Assistant instance.

    Returns:
        Mocked HomeAssistant instance.
    """
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.loop = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry() -> dict[str, Any]:
    """Create a mock config entry.

    Returns:
        Mock config entry dictionary.
    """
    return {
        "entry_id": "test_entry_id",
        "data": {
            "name": "Test Fallback Sensor",
            "entities": ["sensor.test1", "sensor.test2"],
            "unique_id": "test_unique_id",
            "hysteresis_delay": 0,
        },
    }
