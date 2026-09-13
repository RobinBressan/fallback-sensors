# Fallback Sensors for Home Assistant

A custom integration for Home Assistant that creates sensors with automatic fallback. The principle is simple: you define a list of source entities, and the sensor automatically uses the first available one.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=RobinBressan&repository=fallback-sensors&category=integration)

**Or manually:**

1. Add this repository as a custom repository in HACS
2. Search for "Fallback Sensors" in HACS
3. Click "Download"
4. Restart Home Assistant

### Manual installation

1. Copy the `custom_components/fallback_sensors` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

Add the configuration to your `configuration.yaml` file:

```yaml
sensor:
  - platform: fallback_sensors
    name: "Living Room Temperature"
    unique_id: "temp_living_room_fallback"  # Optional, enables UI customization
    entities:
      - sensor.temperature_primary
      - sensor.temperature_zigbee_backup
      - sensor.temperature_wifi_backup
```

### UI configuration

Everything the YAML platform exposes except `conditions` lists of more than one
range and one pattern can also be set from **Settings → Devices & Services →
Add Integration → Fallback Sensors**, and edited afterwards through the entry's
**Configure** button: name, source entities, hysteresis delay, and the
validation conditions (minimum, maximum, pattern). Leaving a condition field
empty disables that condition.

A sensor created through the UI stores a `conditions` list built from those
fields, in the same format as the YAML one.

**Note:** The `unique_id` is optional but recommended. It enables you to customize the entity (name, icon, entity_id) via the Home Assistant UI after creation.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Friendly name displayed in the UI (also used to generate entity_id) |
| `entities` | list | Yes | List of source entities (minimum 2) |
| `unique_id` | string | No | Unique identifier for the sensor (enables UI customization) |
| `hysteresis_delay` | int | No | Delay in seconds before switching (0 = disabled) |
| `conditions` | list | No | List of custom conditions (see below) |

## How it works

### Fallback logic

1. The sensor iterates through the list of entities in order
2. It uses the first entity whose state is **available**
3. An entity is considered **unavailable** if its state is:
   - `unavailable`
   - `unknown`
   - `None`

4. If all entities are unavailable, the sensor becomes `unavailable`

### Hysteresis

With `hysteresis_delay` set to a non-zero value, a switch to another source —
including a switch to `unavailable` when no source is left — is only applied
once the delay has elapsed without the situation improving. If the current
source becomes valid again during the wait, the pending switch is abandoned. If
the source the sensor was heading to becomes invalid too, the delay restarts on
the new target.

Each completed switch counts as exactly one fallback, whether it was applied by
the timer or by a source event received after the delay.

### Feedback loop protection

A fallback sensor writes its own state whenever one of its sources changes. If
a source resolved back to the sensor itself — directly, or through a chain of
other fallback sensors — every write would re-trigger the listener and flood
Home Assistant with state change events.

The integration refuses such configurations:

- the UI setup and options forms reject a source list where the sensor is its
  own source (`self_reference`) or where a selected fallback sensor already
  depends on this one (`circular_reference`);
- a YAML configuration that would loop is not set up, and the reason is logged;
- as a last resort, a looping source found at runtime (for example in a
  configuration stored before this check existed) is dropped from the source
  list with an error in the log, so the sensor keeps working with its remaining
  sources;
- a state event for the sensor's own entity is never acted upon.

Chaining fallback sensors is still supported, as long as the chain does not
come back to its starting point.

### Inherited attributes

The sensor automatically inherits attributes from the active source:
- `unit_of_measurement` (unit of measurement)
- `device_class` (device class)
- `state_class` (state class, **only when it is `measurement`**, see below)
- `icon` (icon)

#### Why `total` and `total_increasing` are not inherited

`measurement` describes an instantaneous reading: the value of the backup
sensor means the same thing as the value of the primary one, so the long term
statistics stay consistent across a switch.

`total` and `total_increasing` describe a *meter*. Its value only makes sense
relative to the counter that produced it, and two counters are never at the
same reading. Forwarding that state class would let the long term statistics
interpret a switch as a real jump — a huge consumption spike when the backup
counter is ahead, or a meter reset when it is behind. Either way the energy
dashboard is corrupted, and long term statistics are not something you can
simply recompute.

So a source declaring `total` or `total_increasing` is still used normally —
its value, unit, device class and icon are forwarded — but the fallback sensor
does not declare a state class and is therefore left out of long term
statistics. If you need statistics on a cumulative source, apply the fallback
upstream (a `utility_meter` or a template sensor fed by the fallback sensor),
where you control how the counters are reconciled.

`measurement_angle`, which describes an instantaneous angle, is treated like
`measurement`.

#### Value type

The state of the active source is exposed as a number when the sensor is a
numeric one (it declares a unit, a numeric device class or a state class), and
as a string otherwise. Integers stay integers, so the rendered value is exactly
the one the source rendered. A value that cannot be converted — or that is
infinite or NaN — is forwarded unchanged rather than dropped.

### Additional attributes

The sensor exposes diagnostic attributes:

```yaml
current_source: sensor.temperature_primary  # Currently used source
source_entities:                             # Complete list of sources
  - sensor.temperature_primary
  - sensor.temperature_zigbee_backup
  - sensor.temperature_wifi_backup
source_index: 0                              # Index of active source (0 = primary)
fallback_count: 3                            # Number of switches since startup
last_fallback_time: "2025-11-07T10:30:00"   # Timestamp of last switch
```

`fallback_count` counts the source switches that happened after the sensor
started: selecting the first source at startup is not a fallback, so a sensor
whose primary source never fails keeps a count of `0`. Both `fallback_count`
and `last_fallback_time` are restored across Home Assistant restarts and entry
reloads, so they measure the reliability of your sources over time rather than
since the last restart. Removing and re-adding the sensor starts over at zero.

```yaml
```

## Usage examples

### Temperature with fallback

```yaml
sensor:
  - platform: fallback_sensors
    name: "House Temperature"
    entities:
      - sensor.temp_thermostat
      - sensor.temp_xiaomi
      - sensor.temp_shelly
```

### Humidity with fallback

```yaml
sensor:
  - platform: fallback_sensors
    name: "Bathroom Humidity"
    entities:
      - sensor.humidity_primary
      - sensor.humidity_backup
```

### Energy consumption

```yaml
sensor:
  - platform: fallback_sensors
    name: "Total Consumption"
    entities:
      - sensor.power_meter_zigbee
      - sensor.power_meter_wifi
      - sensor.power_meter_modbus
```

### With hysteresis (prevents rapid switching)

```yaml
sensor:
  - platform: fallback_sensors
    name: "Stable Temperature"
    hysteresis_delay: 30  # Wait 30 seconds before switching
    entities:
      - sensor.temp_unstable
      - sensor.temp_backup
```

### With custom conditions (valid values)

```yaml
sensor:
  - platform: fallback_sensors
    name: "Valid Temperature"
    entities:
      - sensor.temp_sensor1
      - sensor.temp_sensor2
    conditions:
      - type: range
        min: -20
        max: 50  # Ignore out-of-range values
```

### With regex validation

```yaml
sensor:
  - platform: fallback_sensors
    name: "Sensor State"
    entities:
      - sensor.state1
      - sensor.state2
    conditions:
      - type: regex
        pattern: "^(on|off)$"  # Accept only "on" or "off"
```

## Automations

### Notification on fallback

```yaml
automation:
  - alias: "Temperature sensor fallback alert"
    trigger:
      - platform: state
        entity_id: sensor.living_room_temperature
        attribute: current_source
    condition:
      - condition: template
        value_template: "{{ trigger.from_state.attributes.current_source != trigger.to_state.attributes.current_source }}"
    action:
      - service: notify.mobile_app
        data:
          title: "Temperature sensor switched"
          message: >
            Sensor switched from {{ trigger.from_state.attributes.current_source }}
            to {{ trigger.to_state.attributes.current_source }}
```

### Monitor fallback count

```yaml
automation:
  - alias: "Too many fallbacks"
    trigger:
      - platform: state
        entity_id: sensor.living_room_temperature
        attribute: fallback_count
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.living_room_temperature', 'fallback_count') | int > 10 }}"
    action:
      - service: persistent_notification.create
        data:
          title: "Sensor issue detected"
          message: >
            Sensor {{ trigger.entity_id }} has switched {{ state_attr(trigger.entity_id, 'fallback_count') }} times.
            Check your source sensors.
```

## Debugging

Enable debug logs in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.fallback_sensors: debug
```

Logs will show:
- When a sensor changes source
- When a source becomes unavailable
- Configuration errors

## Use cases

### Problem: Unstable Zigbee sensors
**Solution**: Use a WiFi sensor as backup

```yaml
sensor:
  - platform: fallback_sensors
    name: "Stable Temperature"
    entities:
      - sensor.temp_zigbee  # Sometimes unstable
      - sensor.temp_wifi    # More stable but less accurate
```

### Problem: Sensor maintenance
**Solution**: Keep a backup sensor during replacement

```yaml
sensor:
  - platform: fallback_sensors
    name: "Solar Production"
    entities:
      - sensor.solar_new     # New sensor being tested
      - sensor.solar_old     # Old reliable sensor
```

### Problem: Multiple data sources
**Solution**: Prioritize your sources by reliability

```yaml
sensor:
  - platform: fallback_sensors
    name: "Electricity Price"
    entities:
      - sensor.price_api_provider1  # Main API
      - sensor.price_api_provider2  # Backup API
      - sensor.price_static         # Fixed value as last resort
```

## Limitations and notes

1. **Minimum 2 entities**: Configuration requires at least 2 source entities
2. **No hysteresis by default**: Sensor switches immediately (can be configured)
3. **Mixed types**: You can mix different sensor types, but at your own risk (e.g., temperature → humidity)
4. **Order matters**: Entities are tested in the configured order
5. **No self-reference**: A sensor cannot use itself, or a fallback sensor that
   depends on it, as a source (see *Feedback loop protection*)
6. **No long term statistics on cumulative sources**: `total` and
   `total_increasing` state classes are not forwarded (see *Inherited
   attributes*)

## Support and contributions

- **Issues**: [GitHub Issues](https://github.com/RobinBressan/fallback-sensors/issues)
- **Discussions**: [GitHub Discussions](https://github.com/RobinBressan/fallback-sensors/discussions)
- **Pull Requests**: Contributions are welcome!

## License

MIT License - See LICENSE file for details

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
