"""Feedback-loop protection for Fallback Sensors.

A fallback sensor listens to state changes of its source entities and writes
its own state in response. If a source (directly or through a chain of other
fallback sensors) resolves back to the sensor itself, every write re-triggers
the listener and the instance is flooded with state change events. The helpers
below detect that situation before it can happen.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import async_generate_entity_id

from .const import CONF_ENTITIES, DATA_SOURCES, DOMAIN, ENTITY_ID_FORMAT

ERROR_SELF_REFERENCE = "self_reference"
ERROR_CIRCULAR_REFERENCE = "circular_reference"


@callback
def async_get_source_registry(hass: HomeAssistant) -> dict[str, list[str]]:
    """Return the live map of fallback sensor entity IDs to their sources.

    Args:
        hass: Home Assistant instance.

    Returns:
        Mutable mapping of entity ID to the list of its source entity IDs.
    """
    return hass.data.setdefault(DOMAIN, {}).setdefault(DATA_SOURCES, {})


@callback
def async_register_sources(
    hass: HomeAssistant, entity_id: str, sources: list[str]
) -> None:
    """Declare the sources of a live fallback sensor.

    Args:
        hass: Home Assistant instance.
        entity_id: Entity ID of the fallback sensor.
        sources: Source entity IDs the sensor listens to.
    """
    async_get_source_registry(hass)[entity_id] = list(sources)


@callback
def async_unregister_sources(hass: HomeAssistant, entity_id: str) -> None:
    """Forget the sources of a fallback sensor that is going away.

    Args:
        hass: Home Assistant instance.
        entity_id: Entity ID of the fallback sensor.
    """
    async_get_source_registry(hass).pop(entity_id, None)


@callback
def _async_build_dependency_map(hass: HomeAssistant) -> dict[str, list[str]]:
    """Build the dependency graph of every known fallback sensor.

    Live entities are authoritative; config entries whose entity is not loaded
    (disabled, or an entry that failed to set up) are added from the registry so
    a loop cannot be introduced through them either.

    Args:
        hass: Home Assistant instance.

    Returns:
        Mapping of fallback sensor entity ID to its source entity IDs.
    """
    dependencies = dict(async_get_source_registry(hass))

    entity_registry = er.async_get(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        sources = entry.data.get(CONF_ENTITIES, [])
        for registry_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            dependencies.setdefault(registry_entry.entity_id, list(sources))

    return dependencies


@callback
def async_find_loop(
    hass: HomeAssistant, own_entity_id: str, sources: Iterable[str]
) -> str | None:
    """Check whether a source list would make a sensor depend on itself.

    Args:
        hass: Home Assistant instance.
        own_entity_id: Entity ID of the fallback sensor being configured.
        sources: Source entity IDs that would be configured.

    Returns:
        `ERROR_SELF_REFERENCE` if the sensor is its own source,
        `ERROR_CIRCULAR_REFERENCE` if a source chain leads back to it,
        `None` if the configuration is safe.
    """
    sources = list(sources)
    if own_entity_id in sources:
        return ERROR_SELF_REFERENCE

    dependencies = _async_build_dependency_map(hass)
    # The sensor's own entry must not short-circuit the walk: we are validating
    # a candidate source list, not the one currently stored.
    dependencies.pop(own_entity_id, None)

    seen: set[str] = set()
    queue = deque(sources)
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)

        for dependency in dependencies.get(current, ()):
            if dependency == own_entity_id:
                return ERROR_CIRCULAR_REFERENCE
            queue.append(dependency)

    return None


@callback
def async_resolve_entity_id(
    hass: HomeAssistant, name: str, entry: ConfigEntry | None = None
) -> str:
    """Resolve the entity ID a fallback sensor has, or would be given.

    Args:
        hass: Home Assistant instance.
        name: Configured name of the sensor.
        entry: Config entry of an existing sensor, if any.

    Returns:
        The registered entity ID when the sensor already exists, otherwise the
        entity ID Home Assistant would allocate for it.
    """
    if entry is not None:
        entity_registry = er.async_get(hass)
        registry_entries = er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        if registry_entries:
            return registry_entries[0].entity_id

    return async_generate_entity_id(ENTITY_ID_FORMAT, name, hass=hass)


@callback
def async_filter_sources(
    hass: HomeAssistant, own_entity_id: str, sources: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Split a source list into the safe sources and the looping ones.

    Used as a runtime safety net: YAML sensors and config entries written before
    the flows validated loops must not be able to flood the instance, so the
    offending sources are dropped instead of the whole sensor failing to load.

    Args:
        hass: Home Assistant instance.
        own_entity_id: Entity ID of the fallback sensor.
        sources: Configured source entity IDs.

    Returns:
        Tuple of (safe sources, rejected sources), both preserving order.
    """
    safe: list[str] = []
    rejected: list[str] = []

    for source in sources:
        if async_find_loop(hass, own_entity_id, [source]) is None:
            safe.append(source)
        else:
            rejected.append(source)

    return safe, rejected
