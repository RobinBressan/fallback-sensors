"""Tests for the Fallback Sensors config flow."""

from __future__ import annotations

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.fallback_sensors.const import (
    CONF_ENTITIES,
    CONF_HYSTERESIS_DELAY,
    DOMAIN,
)

from .conftest import BACKUP, PRIMARY


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
