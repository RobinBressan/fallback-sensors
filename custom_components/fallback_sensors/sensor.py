"""Fallback sensor platform for Home Assistant."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    ATTR_CURRENT_SOURCE,
    ATTR_FALLBACK_COUNT,
    ATTR_LAST_FALLBACK_TIME,
    ATTR_SOURCE_ENTITIES,
    ATTR_SOURCE_INDEX,
    CONF_ENTITIES,
    DEFAULT_NAME,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITIES): vol.All(cv.ensure_list, vol.Length(min=2)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Fallback Sensor platform via YAML.

    Args:
        hass: Home Assistant instance.
        config: Configuration dictionary.
        async_add_entities: Callback to add entities.
        discovery_info: Discovery information (unused).
    """
    name: str = config[CONF_NAME]
    entities: list[str] = config[CONF_ENTITIES]
    unique_id: str | None = config.get(CONF_UNIQUE_ID)

    _LOGGER.debug("Setting up fallback sensor '%s' with entities: %s", name, entities)

    sensor = FallbackSensor(hass, name, entities, unique_id)
    async_add_entities([sensor], True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fallback Sensor platform from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry instance.
        async_add_entities: Callback to add entities.
    """
    name: str = entry.data[CONF_NAME]
    entities: list[str] = entry.data[CONF_ENTITIES]
    unique_id: str | None = entry.data.get(CONF_UNIQUE_ID, entry.entry_id)

    _LOGGER.debug(
        "Setting up fallback sensor '%s' from config entry with entities: %s",
        name,
        entities,
    )

    sensor = FallbackSensor(hass, name, entities, unique_id, entry)
    async_add_entities([sensor], True)


class FallbackSensor(SensorEntity):
    """Representation of a Fallback Sensor.

    This sensor monitors multiple source entities and uses the first available one.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entities: list[str],
        unique_id: str | None = None,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the Fallback Sensor.

        Args:
            hass: Home Assistant instance.
            name: Name of the sensor.
            entities: List of entity IDs to use as fallback sources.
            unique_id: Optional unique identifier.
            config_entry: Optional config entry for UI-configured sensors.
        """
        self.hass = hass
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entities = entities
        self._config_entry = config_entry

        # Internal state
        self._attr_native_value: str | None = None
        self._current_source: str | None = None
        self._source_index: int | None = None
        self._fallback_count: int = 0
        self._last_fallback_time: datetime | None = None

        # Attributes from source
        self._attr_native_unit_of_measurement: str | None = None
        self._attr_device_class: str | None = None
        self._attr_state_class: str | None = None
        self._attr_icon: str | None = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added to Home Assistant."""
        # Set up listeners for all source entities
        for entity_id in self._entities:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, entity_id, self._handle_source_change
                )
            )

        # Initialize state
        self._update_from_sources()

        _LOGGER.debug(
            "Fallback sensor '%s' added with %d source entities",
            self.name,
            len(self._entities),
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        """Handle state changes of source entities.

        Args:
            event: State change event.
        """
        _LOGGER.debug(
            "Source entity '%s' changed for fallback sensor '%s'",
            event.data.get("entity_id"),
            self.name,
        )
        self._update_from_sources()
        self.async_write_ha_state()

    def _update_from_sources(self) -> None:
        """Update the sensor state from the first available source entity."""
        previous_source = self._current_source

        # Find the first available source
        active_entity_id, active_state = self._get_active_entity()

        if active_state is None:
            # No available source
            self._attr_native_value = None
            self._current_source = None
            self._source_index = None
            self._attr_available = False

            if previous_source is not None:
                _LOGGER.warning(
                    "No available source for fallback sensor '%s'",
                    self.name,
                )
                self._record_fallback()
        else:
            # Update from active source
            self._attr_native_value = active_state.state
            self._current_source = active_entity_id
            self._source_index = self._entities.index(active_entity_id)
            self._attr_available = True

            # Copy attributes from source
            self._copy_attributes_from_source(active_state)

            # Record fallback if source changed
            if previous_source is not None and previous_source != active_entity_id:
                _LOGGER.info(
                    "Fallback sensor '%s' switched from '%s' to '%s'",
                    self.name,
                    previous_source,
                    active_entity_id,
                )
                self._record_fallback()

    def _get_active_entity(self) -> tuple[str | None, State | None]:
        """Get the first available source entity.

        Returns:
            Tuple of (entity_id, state) for the first available source,
            or (None, None) if no source is available.
        """
        for entity_id in self._entities:
            state = self.hass.states.get(entity_id)

            # Check if state exists and is valid
            if state is None:
                _LOGGER.debug(
                    "Source entity '%s' does not exist for fallback sensor '%s'",
                    entity_id,
                    self.name,
                )
                continue

            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, "None"):
                _LOGGER.debug(
                    "Source entity '%s' is unavailable for fallback sensor '%s'",
                    entity_id,
                    self.name,
                )
                continue

            return entity_id, state

        return None, None

    def _copy_attributes_from_source(self, state: State) -> None:
        """Copy relevant attributes from the source entity state.

        Args:
            state: Source entity state to copy attributes from.
        """
        self._attr_native_unit_of_measurement = state.attributes.get(
            "unit_of_measurement"
        )
        self._attr_device_class = state.attributes.get("device_class")
        self._attr_state_class = state.attributes.get("state_class")
        self._attr_icon = state.attributes.get("icon")

    def _record_fallback(self) -> None:
        """Record a fallback event."""
        self._fallback_count += 1
        self._last_fallback_time = datetime.now()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes.

        Returns:
            Dictionary of additional attributes.
        """
        return {
            ATTR_CURRENT_SOURCE: self._current_source,
            ATTR_SOURCE_ENTITIES: self._entities,
            ATTR_SOURCE_INDEX: self._source_index,
            ATTR_FALLBACK_COUNT: self._fallback_count,
            ATTR_LAST_FALLBACK_TIME: (
                self._last_fallback_time.isoformat()
                if self._last_fallback_time
                else None
            ),
        }
