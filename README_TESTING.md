# Docker Testing Guide

This guide explains how to test the Fallback Sensors integration locally with Docker.

## Prerequisites

- Docker installed
- Docker Compose installed

## Quick start

```bash
# 1. Start Home Assistant
docker-compose up -d

# 2. Follow the logs
docker-compose logs -f homeassistant

# 3. Access Home Assistant
# Open http://localhost:8123
# First start: create a user account
```

## Test configuration

### Simulated sensors

The test environment includes 3 simulated temperature sensors:
- `sensor.test_temp_primary`: Primary sensor (20-25°C)
- `sensor.test_temp_backup`: Backup sensor (18-21°C)
- `sensor.test_temp_fallback`: Fallback sensor (22-24°C)

### Pre-configured fallback sensor

A fallback sensor is pre-configured in `test-config/configuration.yaml`:
```yaml
sensor:
  - platform: fallback_sensors
    name: "Temperature Fallback Test"
    hysteresis_delay: 5
    entities:
      - sensor.test_temp_primary
      - sensor.test_temp_backup
      - sensor.test_temp_fallback
    conditions:
      - type: range
        min: 15
        max: 30
```

## Manual tests

### Test 1: UI configuration

1. **Settings** → **Devices & Services**
2. **Add Integration**
3. Search for **"Fallback Sensors"**
4. Configure:
   - Name: "My test sensor"
   - Entities: select 2+ sensors
   - Hysteresis: 10 seconds
5. Verify the sensor appears in **States**

### Test 2: Automatic fallback

1. Go to **Developer Tools** → **States**
2. Observe the state of `sensor.temperature_fallback_test`
3. Verify attributes:
   - `current_source`: should be `sensor.test_temp_primary`
   - `source_index`: should be `0`
   - `fallback_count`: should be `0` at start

### Test 3: Simulate failure

To simulate primary sensor failure, modify `test-config/configuration.yaml` and force an unavailable state (requires restart).

Or via developer tools:
1. **Developer Tools** → **States**
2. Find `sensor.test_temp_primary`
3. Temporarily modify the state (doesn't persist)

### Test 4: Hysteresis

1. Observe the fallback sensor
2. Temporarily disable the primary sensor
3. The fallback sensor should wait 5 seconds before switching
4. Check logs: `docker-compose logs -f homeassistant | grep fallback`

### Test 5: Custom conditions

The test sensor has a `range: 15-30°C` condition.

To test:
1. Modify `test-config/configuration.yaml`
2. Change a sensor value to be out of range
3. Restart: `docker-compose restart`
4. Observe that the sensor is ignored

## Log verification

```bash
# Real-time logs
docker-compose logs -f homeassistant

# Filter only fallback_sensors
docker-compose logs -f homeassistant | grep fallback_sensors

# Complete logs
docker-compose logs homeassistant
```

Expected logs:
```
DEBUG (MainThread) [custom_components.fallback_sensors] Setting up fallback sensor 'Temperature Fallback Test'
INFO (MainThread) [custom_components.fallback_sensors.sensor] Fallback sensor 'Temperature Fallback Test' switched to 'sensor.test_temp_primary'
```

## Real-time modifications

The integration is mounted read-only from the source code:
```yaml
volumes:
  - ./custom_components/fallback_sensors:/config/custom_components/fallback_sensors:ro
```

To test modifications:
1. Modify the code in `custom_components/fallback_sensors/`
2. Restart the container: `docker-compose restart`
3. Changes are immediately applied

## Cleanup

```bash
# Stop Home Assistant
docker-compose down

# Remove test data (database, logs, etc.)
rm -rf test-config/.storage test-config/*.db* test-config/*.log

# Clean restart
docker-compose up -d
```

## Debugging

### Home Assistant won't start

```bash
# Check logs
docker-compose logs homeassistant

# Verify configuration
docker-compose exec homeassistant python -m homeassistant --script check_config -c /config
```

### Integration doesn't appear

1. Verify the folder is mounted:
   ```bash
   docker-compose exec homeassistant ls -la /config/custom_components/fallback_sensors
   ```

2. Check manifest.json:
   ```bash
   docker-compose exec homeassistant cat /config/custom_components/fallback_sensors/manifest.json
   ```

3. Restart:
   ```bash
   docker-compose restart
   ```

### Python errors

```bash
# Interactive shell in container
docker-compose exec homeassistant bash

# Test Python import
python3 -c "from custom_components.fallback_sensors.sensor import FallbackSensor; print('OK')"
```

## Configuration file access

Configuration files are in `test-config/`:
- `configuration.yaml`: Main configuration
- `automations.yaml`: Automations
- `scripts.yaml`: Scripts
- `scenes.yaml`: Scenes

Modify these files and restart to test different configurations.

## Web interface

Home Assistant is accessible at: **http://localhost:8123**

On first start:
1. Create a user account
2. Configure name and location
3. Accept default settings

## Advanced tests

### Test regex conditions

Add to `test-config/configuration.yaml`:
```yaml
sensor:
  - platform: fallback_sensors
    name: "State Pattern Test"
    entities:
      - input_boolean.test_primary_available
      - input_boolean.test_backup_available
    conditions:
      - type: regex
        pattern: "^on$"
```

### Test fallback_count

Create an automation that counts fallbacks:
```yaml
automation:
  - alias: "Count Fallbacks"
    trigger:
      - platform: state
        entity_id: sensor.temperature_fallback_test
        attribute: fallback_count
    action:
      - service: persistent_notification.create
        data:
          title: "Fallback detected"
          message: "Sensor has switched {{ trigger.to_state.attributes.fallback_count }} times"
```

## Useful commands

```bash
# Start in background
docker-compose up -d

# Stop
docker-compose down

# Restart
docker-compose restart

# View logs
docker-compose logs -f

# Shell in container
docker-compose exec homeassistant bash

# Rebuild image
docker-compose pull
docker-compose up -d --force-recreate
```
