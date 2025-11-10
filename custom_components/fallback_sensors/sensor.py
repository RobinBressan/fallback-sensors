"""Fallback sensor platform for Home Assistant."""

from __future__ import annotations

import asyncio
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

from .conditions import ConditionValidator
from .const import (
    ATTR_CURRENT_SOURCE,
    ATTR_FALLBACK_COUNT,
    ATTR_LAST_FALLBACK_TIME,
    ATTR_SOURCE_ENTITIES,
    ATTR_SOURCE_INDEX,
    CONF_CONDITIONS,
    CONF_ENTITIES,
    CONF_HYSTERESIS_DELAY,
    DEFAULT_HYSTERESIS_DELAY,
    DEFAULT_NAME,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITIES): vol.All(cv.ensure_list, vol.Length(min=2)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(
            CONF_HYSTERESIS_DELAY, default=DEFAULT_HYSTERESIS_DELAY
        ): cv.positive_int,
        vol.Optional(CONF_CONDITIONS): vol.All(cv.ensure_list, [dict]),
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
    hysteresis_delay: int = config[CONF_HYSTERESIS_DELAY]
    conditions: list[dict[str, Any]] | None = config.get(CONF_CONDITIONS)

    _LOGGER.debug("Setting up fallback sensor '%s' with entities: %s", name, entities)

    sensor = FallbackSensor(
        hass, name, entities, unique_id, None, hysteresis_delay, conditions
    )
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
    hysteresis_delay: int = entry.data.get(
        CONF_HYSTERESIS_DELAY, DEFAULT_HYSTERESIS_DELAY
    )
    conditions: list[dict[str, Any]] | None = entry.data.get(CONF_CONDITIONS)

    _LOGGER.debug(
        "Setting up fallback sensor '%s' from config entry with entities: %s",
        name,
        entities,
    )

    sensor = FallbackSensor(
        hass, name, entities, unique_id, entry, hysteresis_delay, conditions
    )
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
        hysteresis_delay: int = DEFAULT_HYSTERESIS_DELAY,
        conditions: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the Fallback Sensor.

        Args:
            hass: Home Assistant instance.
            name: Name of the sensor.
            entities: List of entity IDs to use as fallback sources.
            unique_id: Optional unique identifier.
            config_entry: Optional config entry for UI-configured sensors.
            hysteresis_delay: Delay in seconds before switching sources (0 = disabled).
            conditions: Optional list of validation conditions.
        """
        self.hass = hass
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entities = entities
        self._config_entry = config_entry
        self._hysteresis_delay = hysteresis_delay
        self._condition_validator = ConditionValidator(conditions)

        # Set entity_id based on unique_id if provided, otherwise use name
        if unique_id:
            self.entity_id = f"sensor.{unique_id}"

        # Internal state
        self._attr_native_value: str | None = None
        self._current_source: str | None = None
        self._source_index: int | None = None
        self._fallback_count: int = 0
        self._last_fallback_time: datetime | None = None

        # Hysteresis tracking
        self._pending_source: str | None = None
        self._pending_since: datetime | None = None
        self._hysteresis_timer: Any = None

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

        # Check if source would change
        if active_entity_id != previous_source:
            self._handle_source_change_with_hysteresis(
                active_entity_id, active_state, previous_source
            )
        else:
            # Same source, cancel any pending changes
            self._cancel_hysteresis_timer()
            self._pending_source = None
            self._pending_since = None

            # Update state from current source
            if active_state is not None:
                self._apply_source_state(active_entity_id, active_state, False)
            else:
                self._set_unavailable(previous_source)

    def _handle_source_change_with_hysteresis(
        self,
        new_source: str | None,
        new_state: State | None,
        previous_source: str | None,
    ) -> None:
        """Handle source change with hysteresis delay.

        Args:
            new_source: New source entity ID.
            new_state: New source state.
            previous_source: Previous source entity ID.
        """
        # If hysteresis is disabled or this is the first source, apply immediately
        if self._hysteresis_delay == 0 or previous_source is None:
            if new_state is not None:
                self._apply_source_state(new_source, new_state, True)
            else:
                self._set_unavailable(previous_source)
            return

        # Check if we're already tracking a pending change to this source
        if self._pending_source == new_source:
            # Check if enough time has passed
            if self._pending_since is not None:
                elapsed = (datetime.now() - self._pending_since).total_seconds()
                if elapsed >= self._hysteresis_delay:
                    # Time has passed, apply the change
                    self._cancel_hysteresis_timer()
                    if new_state is not None:
                        self._apply_source_state(new_source, new_state, True)
                    else:
                        self._set_unavailable(previous_source)
            return

        # New pending source, start tracking
        self._cancel_hysteresis_timer()
        self._pending_source = new_source
        self._pending_since = datetime.now()

        _LOGGER.debug(
            "Fallback sensor '%s': pending switch from '%s' to '%s' (delay: %ds)",
            self.name,
            previous_source,
            new_source,
            self._hysteresis_delay,
        )

        # Schedule the change
        self._hysteresis_timer = self.hass.loop.call_later(
            self._hysteresis_delay,
            lambda: asyncio.create_task(self._apply_pending_source()),
        )

    async def _apply_pending_source(self) -> None:
        """Apply the pending source change after hysteresis delay."""
        if self._pending_source is None:
            return

        _LOGGER.info(
            "Fallback sensor '%s': applying pending switch to '%s'",
            self.name,
            self._pending_source,
        )

        # Re-check the active source
        active_entity_id, active_state = self._get_active_entity()

        if active_state is not None:
            self._apply_source_state(active_entity_id, active_state, True)
        else:
            self._set_unavailable(self._current_source)

        self._pending_source = None
        self._pending_since = None
        self.async_write_ha_state()

    def _cancel_hysteresis_timer(self) -> None:
        """Cancel any pending hysteresis timer."""
        if self._hysteresis_timer is not None:
            self._hysteresis_timer.cancel()
            self._hysteresis_timer = None

    def _apply_source_state(
        self, entity_id: str, state: State, record_fallback: bool
    ) -> None:
        """Apply state from a source entity.

        Args:
            entity_id: Source entity ID.
            state: Source state.
            record_fallback: Whether to record this as a fallback event.
        """
        self._attr_native_value = state.state
        self._current_source = entity_id
        self._source_index = self._entities.index(entity_id)
        self._attr_available = True

        # Copy attributes from source
        self._copy_attributes_from_source(state)

        if record_fallback:
            _LOGGER.info(
                "Fallback sensor '%s' switched to '%s'",
                self.name,
                entity_id,
            )
            self._record_fallback()

    def _set_unavailable(self, previous_source: str | None) -> None:
        """Set sensor as unavailable.

        Args:
            previous_source: Previous source entity ID.
        """
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

            # Check custom conditions
            if not self._condition_validator.is_valid(state):
                _LOGGER.debug(
                    "Source entity '%s' does not meet conditions for fallback sensor '%s'",
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
