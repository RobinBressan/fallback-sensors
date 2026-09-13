# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-09-13

Robustness release, targeting Home Assistant 2026.7.x. Every change is either a
bug fix or a guard rail; the fallback logic itself — first valid source of an
ordered list, hysteresis before switching, range and regex conditions,
traceability attributes — is unchanged.

### Fixed

- **The options flow could not be opened.** It assigned `self.config_entry`,
  whose setter no longer exists, so editing a sensor from the UI raised
  `AttributeError`. The entry now comes from the base class property.
- **Saving the options form destroyed part of the configuration.** The entry
  data was replaced by the submitted fields, silently dropping `unique_id`
  (which changes the entity's identity) and `conditions`. Unexposed keys are
  preserved.
- **A source switch could be counted twice.** When a source event arrived after
  the hysteresis delay had elapsed, the switch was applied without clearing the
  pending state, and the timer applied it again — incrementing `fallback_count`
  twice for a single switch. There is now a single application path.
- **A pending switch to "no source at all" never completed.** With hysteresis
  enabled, losing the last source left the sensor showing a stale value until
  another state event happened to arrive — which, for a dead source, may be
  never.
- **The hysteresis timer bypassed Home Assistant's scheduler.** It used
  `hass.loop.call_later` wrapping a task creation, which races with incoming
  events and ignores Home Assistant's clock. It now uses `async_call_later`,
  and is cancelled when the entity is removed.
- **`fallback_count` started at 1.** Selecting the first source at startup was
  recorded as a fallback, so every restart added one and refreshed
  `last_fallback_time` even though nothing had failed.
- **Long term statistics were corrupted for cumulative sources.** `state_class`
  was copied verbatim, so switching between two `total` / `total_increasing`
  counters was recorded as a real jump. Only `measurement` and
  `measurement_angle` are forwarded now; see the README for the reasoning.
- **The value was always a string.** Home Assistant expects a number from a
  sensor declaring a unit, a numeric device class or a state class. It is now
  converted, integers staying integers so the rendered state is unchanged.
- **Translations were never displayed.** Home Assistant reads
  `translations/en.json` for custom integrations, and the file did not exist.

### Added

- **Feedback loop protection.** A source resolving back to the sensor itself,
  directly or through a chain of fallback sensors, makes every state write
  re-trigger the sensor's own listener and floods the instance with events.
  Such a configuration is now refused by both flows, refused at YAML setup, and
  neutralised at runtime as a last resort; the sensor never reacts to its own
  state events.
- **Range and regex conditions in the UI**, on the setup and options forms,
  with validation of the bounds and of the pattern.
- **Persistent counters.** `fallback_count` and `last_fallback_time` survive a
  restart or a reload.
- **A test suite** running against a real Home Assistant instance
  (`pytest-homeassistant-custom-component`, pinned to the release shipping
  Home Assistant 2026.7.4), plus `hassfest` and `ruff` in CI.

### Changed

- Config entry version raised to 2. Existing entries are migrated
  automatically; an entry written by a newer version is refused rather than
  loaded with unknown data.
- The event listener and the timer callback can no longer let an exception
  escape.
- `should_poll` is disabled: the sensor is entirely event driven, and polling
  only re-wrote an unchanged state every 30 seconds.
- Minimum supported Home Assistant version raised to 2026.7.0.
- `manifest.json` now carries the released version. It had been left at
  `1.0.0` while 1.1.0, 1.1.1 and 1.1.2 were tagged, so Home Assistant reported
  a version that had not been installed for three releases.

### Upgrade notes

- `fallback_count` reads one lower than before for sensors that never switched,
  and is no longer reset by a restart.
- A fallback sensor over `total` / `total_increasing` sources loses its
  `state_class` and disappears from long term statistics. The statistics it
  produced were wrong; existing ones are worth deleting from
  **Developer Tools → Statistics**.
- Source lists that would create a feedback loop are refused. Such a
  configuration was never usable.

## [1.1.2] - 2025-11-10

### Fixed

- Infinite reload loop when the integration was updated from the UI: the update
  listener was re-registered on every reload.

## [1.1.1] - 2025-11-10

### Fixed

- Crash when updating the integration from the UI.
- Several stability fixes for production use.

### Changed

- Reverted the generation of the entity ID from `unique_id`.

## [1.1.0] - 2025-11-10

### Fixed

- `hacs.json` format, for HACS validation.

## [1.0.0] - 2025-11-07

- Initial release
- Sequential fallback logic
- Automatic attribute copying
- Event-driven listeners
- Diagnostic attributes
- UI configuration support (Config Flow)
- Hysteresis support (0-300 seconds)
- Custom conditions (range and regex)

[2.0.0]: https://github.com/RobinBressan/fallback-sensors/releases/tag/2.0.0
[1.1.2]: https://github.com/RobinBressan/fallback-sensors/releases/tag/1.1.2
[1.1.1]: https://github.com/RobinBressan/fallback-sensors/releases/tag/1.1.1
[1.1.0]: https://github.com/RobinBressan/fallback-sensors/releases/tag/1.1.0
[1.0.0]: https://github.com/RobinBressan/fallback-sensors/releases/tag/v1.0.0
