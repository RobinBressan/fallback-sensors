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
    unique_id: "temp_living_room_fallback"  # Creates sensor.temp_living_room_fallback
    entities:
      - sensor.temperature_primary
      - sensor.temperature_zigbee_backup
      - sensor.temperature_wifi_backup
```

**Note:** If `unique_id` is provided, it will be used to generate the entity_id (`sensor.<unique_id>`). If omitted, the entity_id will be generated from the `name` parameter.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Friendly name displayed in the UI |
| `entities` | list | Yes | List of source entities (minimum 2) |
| `unique_id` | string | No | Unique identifier - also used to generate entity_id (e.g., `unique_id: temp_room` → `sensor.temp_room`) |
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

### Inherited attributes

The sensor automatically inherits attributes from the active source:
- `unit_of_measurement` (unit of measurement)
- `device_class` (device class)
- `state_class` (state class)
- `icon` (icon)

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

## Support and contributions

- **Issues**: [GitHub Issues](https://github.com/RobinBressan/fallback-sensors/issues)
- **Discussions**: [GitHub Discussions](https://github.com/RobinBressan/fallback-sensors/discussions)
- **Pull Requests**: Contributions are welcome!

## License

MIT License - See LICENSE file for details

## Changelog

### v1.0.0 (2025-11-07)
- Initial release
- Sequential fallback logic
- Automatic attribute copying
- Event-driven listeners
- Diagnostic attributes
- UI configuration support (Config Flow)
- Hysteresis support (0-300 seconds)
- Custom conditions (range and regex)
- Comprehensive unit tests
