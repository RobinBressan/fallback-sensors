"""Fallback sensor platform for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import math
from typing import Any, Final

from homeassistant.components.sensor import (
    NON_NUMERIC_DEVICE_CLASSES,
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util
import voluptuous as vol

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
from .loop_guard import (
    async_filter_sources,
    async_find_loop,
    async_register_sources,
    async_resolve_entity_id,
    async_unregister_sources,
)

_LOGGER = logging.getLogger(__name__)

# State classes that survive a source switch. `total` and `total_increasing`
# describe a meter whose value only makes sense relative to the counter that
# produced it: switching between two counters makes the long term statistics
# jump, so the state class is dropped instead of being propagated.
FORWARDED_STATE_CLASSES: Final = frozenset(
    {
        SensorStateClass.MEASUREMENT,
        SensorStateClass.MEASUREMENT_ANGLE,
    }
)

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

    own_entity_id = async_resolve_entity_id(hass, name)
    if error := async_find_loop(hass, own_entity_id, entities):
        _LOGGER.error(
            "Refusing to set up fallback sensor '%s': its source list would make "
            "it depend on itself (%s). Fix the 'entities' list in your YAML "
            "configuration",
            name,
            error,
        )
        return

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


@dataclass
class FallbackSensorExtraStoredData(ExtraStoredData):
    """Traceability counters kept across restarts."""

    fallback_count: int
    last_fallback_time: datetime | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable representation.

        Returns:
            Dictionary stored by the restore state helper.
        """
        return {
            "fallback_count": self.fallback_count,
            "last_fallback_time": (
                self.last_fallback_time.isoformat() if self.last_fallback_time else None
            ),
        }

    @classmethod
    def from_dict(
        cls, restored: dict[str, Any]
    ) -> FallbackSensorExtraStoredData | None:
        """Rebuild the counters from a stored representation.

        Args:
            restored: Dictionary previously produced by `as_dict`.

        Returns:
            The restored counters, or None when the data is unusable.
        """
        try:
            fallback_count = int(restored["fallback_count"])
        except (KeyError, TypeError, ValueError):
            return None

        raw_time = restored.get("last_fallback_time")
        last_fallback_time = dt_util.parse_datetime(raw_time) if raw_time else None

        return cls(fallback_count, last_fallback_time)


class FallbackSensor(RestoreEntity, SensorEntity):
    """Representation of a Fallback Sensor.

    This sensor monitors multiple source entities and uses the first available one.
    """

    # Fully event driven: the state is recomputed from source state changes.
    _attr_should_poll = False

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

        # Internal state
        self._attr_native_value: int | float | str | None = None
        self._current_source: str | None = None
        self._source_index: int | None = None
        self._fallback_count: int = 0
        self._last_fallback_time: datetime | None = None

        # Hysteresis tracking. A switch is pending if, and only if,
        # `_pending_since` is set: `_pending_source` may legitimately be None,
        # meaning "no source left, go unavailable once the delay has elapsed".
        self._pending_source: str | None = None
        self._pending_since: datetime | None = None
        self._hysteresis_timer: CALLBACK_TYPE | None = None
        self._initialized: bool = False

        # Attributes from source
        self._attr_native_unit_of_measurement: str | None = None
        self._attr_device_class: str | None = None
        self._attr_state_class: SensorStateClass | str | None = None
        self._attr_icon: str | None = None

    @property
    def extra_restore_state_data(self) -> FallbackSensorExtraStoredData:
        """Return the counters to store for the next restart.

        Returns:
            Traceability counters of this sensor.
        """
        return FallbackSensorExtraStoredData(
            self._fallback_count, self._last_fallback_time
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        await self._async_restore_counters()

        # Last line of defence against a state event feedback loop: a source
        # that resolves back to this sensor is dropped rather than listened to.
        safe, rejected = async_filter_sources(self.hass, self.entity_id, self._entities)
        if rejected:
            _LOGGER.error(
                "Fallback sensor '%s' ignores the source(s) %s: they would make "
                "the sensor depend on its own state",
                self.entity_id,
                ", ".join(rejected),
            )
            self._entities = safe

        async_register_sources(self.hass, self.entity_id, self._entities)

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

    async def _async_restore_counters(self) -> None:
        """Restore the traceability counters from the previous run."""
        if (last_extra_data := await self.async_get_last_extra_data()) is None:
            return

        restored = FallbackSensorExtraStoredData.from_dict(last_extra_data.as_dict())
        if restored is None:
            _LOGGER.debug(
                "Fallback sensor '%s' could not restore its counters", self.entity_id
            )
            return

        self._fallback_count = restored.fallback_count
        self._last_fallback_time = restored.last_fallback_time

        _LOGGER.debug(
            "Fallback sensor '%s' restored %d fallback(s), last one at %s",
            self.entity_id,
            self._fallback_count,
            self._last_fallback_time,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed from Home Assistant."""
        # Cancel any pending hysteresis timer
        self._clear_pending_source()

        async_unregister_sources(self.hass, self.entity_id)

        _LOGGER.debug(
            "Fallback sensor '%s' removed",
            self.name,
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        """Handle state changes of source entities.

        Args:
            event: State change event.
        """
        try:
            entity_id = event.data.get("entity_id")
            if entity_id == self.entity_id:
                # Never react to our own state writes: that is the feedback loop
                # the loop guard exists to prevent.
                _LOGGER.error(
                    "Fallback sensor '%s' received its own state change event and "
                    "ignored it",
                    self.entity_id,
                )
                return

            _LOGGER.debug(
                "Source entity '%s' changed for fallback sensor '%s'",
                entity_id,
                self.name,
            )
            self._update_from_sources()
            self.async_write_ha_state()
        except Exception:  # an event listener must never raise
            _LOGGER.exception(
                "Unexpected error while handling a source change for fallback "
                "sensor '%s'",
                self.entity_id,
            )

    def _update_from_sources(self) -> None:
        """Recompute the sensor state from the ordered list of sources.

        Decides whether the switch happens now or after the hysteresis delay,
        but never applies it twice: `_apply_active_source` is the only place
        where the state, the current source and the fallback counter change.
        """
        previous_source = self._current_source
        active_entity_id, active_state = self._get_active_entity()

        if active_entity_id == previous_source:
            # Same source: abandon any pending switch and refresh the value.
            self._clear_pending_source()
            self._apply_active_source(
                active_entity_id, active_state, previous_source, record_fallback=False
            )
            return

        if self._hysteresis_delay == 0 or not self._initialized:
            # Hysteresis disabled, or first evaluation: apply straight away.
            self._clear_pending_source()
            self._apply_active_source(
                active_entity_id,
                active_state,
                previous_source,
                record_fallback=self._initialized,
            )
            return

        if self._pending_since is not None and self._pending_source == active_entity_id:
            # Already waiting for this exact switch; the timer will apply it.
            return

        self._start_pending_source(active_entity_id, previous_source)

    def _start_pending_source(
        self, new_source: str | None, previous_source: str | None
    ) -> None:
        """Arm the hysteresis timer for a switch to `new_source`.

        Args:
            new_source: Source entity ID to switch to, None to go unavailable.
            previous_source: Source entity ID currently in use.
        """
        self._clear_pending_source()
        self._pending_source = new_source
        self._pending_since = dt_util.utcnow()

        _LOGGER.debug(
            "Fallback sensor '%s': pending switch from '%s' to '%s' (delay: %ds)",
            self.name,
            previous_source,
            new_source,
            self._hysteresis_delay,
        )

        self._hysteresis_timer = async_call_later(
            self.hass,
            self._hysteresis_delay,
            self._async_hysteresis_elapsed,
        )

    @callback
    def _async_hysteresis_elapsed(self, _now: datetime) -> None:
        """Apply the pending switch once the hysteresis delay has elapsed.

        Args:
            _now: Time the timer fired (unused).
        """
        # The timer has fired: its cancel callback is spent.
        self._hysteresis_timer = None

        try:
            if self._pending_since is None:
                # The switch was abandoned before the timer fired.
                return

            _LOGGER.info(
                "Fallback sensor '%s': applying pending switch to '%s'",
                self.name,
                self._pending_source,
            )
            self._clear_pending_source()

            # Re-read the sources: the situation may have changed during the
            # delay, and only a real switch counts as a fallback.
            previous_source = self._current_source
            active_entity_id, active_state = self._get_active_entity()
            self._apply_active_source(
                active_entity_id,
                active_state,
                previous_source,
                record_fallback=active_entity_id != previous_source,
            )
            self.async_write_ha_state()
        except Exception:  # a timer callback must never raise
            _LOGGER.exception(
                "Unexpected error while applying the pending source of fallback "
                "sensor '%s'",
                self.entity_id,
            )

    def _clear_pending_source(self) -> None:
        """Drop any pending switch and cancel its timer."""
        if self._hysteresis_timer is not None:
            self._hysteresis_timer()
            self._hysteresis_timer = None

        self._pending_source = None
        self._pending_since = None

    def _apply_active_source(
        self,
        entity_id: str | None,
        state: State | None,
        previous_source: str | None,
        *,
        record_fallback: bool,
    ) -> None:
        """Apply the resolved source to the sensor state.

        Args:
            entity_id: Resolved source entity ID, None when none is valid.
            state: State of the resolved source, None when none is valid.
            previous_source: Source entity ID in use before this update.
            record_fallback: Whether this update counts as a fallback event.
        """
        self._initialized = True

        if state is not None and entity_id is not None:
            self._apply_source_state(entity_id, state, record_fallback)
        else:
            self._set_unavailable(previous_source, record_fallback)

    def _apply_source_state(
        self, entity_id: str, state: State, record_fallback: bool
    ) -> None:
        """Apply state from a source entity.

        Args:
            entity_id: Source entity ID.
            state: Source state.
            record_fallback: Whether to record this as a fallback event.
        """
        self._current_source = entity_id
        self._source_index = self._entities.index(entity_id)
        self._attr_available = True

        # Copy attributes from source first: whether the value is expected to
        # be numeric depends on them.
        self._copy_attributes_from_source(state)
        self._attr_native_value = self._parse_native_value(state.state)

        if record_fallback:
            _LOGGER.info(
                "Fallback sensor '%s' switched to '%s'",
                self.name,
                entity_id,
            )
            self._record_fallback()

    def _set_unavailable(
        self, previous_source: str | None, record_fallback: bool
    ) -> None:
        """Set sensor as unavailable.

        Args:
            previous_source: Previous source entity ID.
            record_fallback: Whether losing the source counts as a fallback.
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

        if record_fallback and previous_source is not None:
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
                    "Source entity '%s' does not meet conditions for "
                    "fallback sensor '%s'",
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
        self._attr_icon = state.attributes.get("icon")

        state_class = state.attributes.get("state_class")
        if state_class is None or state_class in FORWARDED_STATE_CLASSES:
            self._attr_state_class = state_class
        else:
            # A cumulative state class must not follow a source switch: see
            # FORWARDED_STATE_CLASSES.
            _LOGGER.debug(
                "Fallback sensor '%s' does not propagate the '%s' state class "
                "of source '%s'",
                self.name,
                state_class,
                state.entity_id,
            )
            self._attr_state_class = None

    def _numeric_state_expected(self) -> bool:
        """Tell whether Home Assistant expects a numeric value for this sensor.

        Mirrors the rule Home Assistant applies to sensor entities, based on the
        attributes this sensor exposes after copying them from its source.

        Returns:
            True when the state must be numeric.
        """
        if self._attr_device_class in NON_NUMERIC_DEVICE_CLASSES:
            return False

        return (
            self._attr_state_class is not None
            or self._attr_native_unit_of_measurement is not None
            or self._attr_device_class is not None
        )

    def _parse_native_value(self, value: str) -> int | float | str:
        """Convert a source state to the type Home Assistant expects.

        Integers are parsed as integers so the state is rendered exactly as the
        source rendered it: `"7"` stays `7`, not `7.0`.

        Args:
            value: Raw state string of the source entity.

        Returns:
            The value as an int or a float when the sensor is expected to be
            numeric and the conversion succeeds, the original string otherwise.
        """
        if not self._numeric_state_expected():
            return value

        try:
            return int(value)
        except (TypeError, ValueError):
            pass

        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Fallback sensor '%s' keeps the non numeric state '%s' as is",
                self.name,
                value,
            )
            return value

        if not math.isfinite(numeric_value):
            _LOGGER.debug(
                "Fallback sensor '%s' keeps the non finite state '%s' as is",
                self.name,
                value,
            )
            return value

        return numeric_value

    def _record_fallback(self) -> None:
        """Record a fallback event."""
        self._fallback_count += 1
        self._last_fallback_time = dt_util.utcnow()

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
