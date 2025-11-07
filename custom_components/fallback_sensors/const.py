"""Constants for the Fallback Sensors integration."""

from typing import Final

# Domain
DOMAIN: Final = "fallback_sensors"

# Configuration keys
CONF_ENTITIES: Final = "entities"
CONF_HYSTERESIS_DELAY: Final = "hysteresis_delay"

# Attribute keys
ATTR_CURRENT_SOURCE: Final = "current_source"
ATTR_SOURCE_ENTITIES: Final = "source_entities"
ATTR_SOURCE_INDEX: Final = "source_index"
ATTR_FALLBACK_COUNT: Final = "fallback_count"
ATTR_LAST_FALLBACK_TIME: Final = "last_fallback_time"

# Default values
DEFAULT_NAME: Final = "Fallback Sensor"
DEFAULT_HYSTERESIS_DELAY: Final = 0  # seconds, 0 = disabled
