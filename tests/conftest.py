"""Pytest configuration and fixtures for Fallback Sensors tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fallback_sensors.const import (
    CONF_ENTITIES,
    CONF_HYSTERESIS_DELAY,
    DOMAIN,
)

TEST_NAME = "Test Fallback"
TEST_ENTITY_ID = "sensor.test_fallback"
PRIMARY = "sensor.primary"
BACKUP = "sensor.backup"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading of the custom integration in every test."""
    return


@pytest.fixture
def build_entry() -> Callable[..., MockConfigEntry]:
    """Return a factory building a config entry for the integration."""

    def _build(
        entities: list[str] | None = None,
        *,
        name: str = TEST_NAME,
        hysteresis_delay: int = 0,
        **extra: Any,
    ) -> MockConfigEntry:
        data: dict[str, Any] = {
            "name": name,
            CONF_ENTITIES: entities if entities is not None else [PRIMARY, BACKUP],
            CONF_HYSTERESIS_DELAY: hysteresis_delay,
            **extra,
        }
        return MockConfigEntry(domain=DOMAIN, title=name, data=data)

    return _build


@pytest.fixture
def setup_entry(
    hass: HomeAssistant, build_entry: Callable[..., MockConfigEntry]
) -> Callable[..., Any]:
    """Return a coroutine factory adding and setting up a config entry."""

    async def _setup(**kwargs: Any) -> MockConfigEntry:
        entry = build_entry(**kwargs)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup
