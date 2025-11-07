# Fallback Sensors for Home Assistant

Une intégration custom pour Home Assistant qui permet de créer des capteurs avec fallback automatique. Le principe est simple : vous définissez une liste d'entités sources, et le capteur utilise automatiquement la première qui est disponible.

## Installation

### HACS (recommandé)

1. Ajoutez ce repository comme repository custom dans HACS
2. Recherchez "Fallback Sensors" dans HACS
3. Cliquez sur "Télécharger"
4. Redémarrez Home Assistant

### Installation manuelle

1. Copiez le dossier `custom_components/fallback_sensors` dans votre dossier `config/custom_components/`
2. Redémarrez Home Assistant

## Configuration

Ajoutez la configuration dans votre fichier `configuration.yaml` :

```yaml
sensor:
  - platform: fallback_sensors
    name: "Température Salon"
    unique_id: "temp_salon_fallback"  # optionnel
    entities:
      - sensor.temperature_primary
      - sensor.temperature_zigbee_backup
      - sensor.temperature_wifi_backup
```

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `name` | string | Oui | Nom du capteur fallback |
| `entities` | list | Oui | Liste d'entités sources (minimum 2) |
| `unique_id` | string | Non | Identifiant unique du capteur |

## Fonctionnement

### Logique de fallback

1. Le capteur parcourt la liste d'entités dans l'ordre
2. Il utilise la première entité dont l'état est **disponible**
3. Une entité est considérée **indisponible** si son état est :
   - `unavailable`
   - `unknown`
   - `None`

4. Si toutes les entités sont indisponibles, le capteur passe en état `unavailable`

### Attributs copiés

Le capteur hérite automatiquement des attributs de la source active :
- `unit_of_measurement` (unité de mesure)
- `device_class` (classe d'appareil)
- `state_class` (classe d'état)
- `icon` (icône)

### Attributs supplémentaires

Le capteur expose des attributs de diagnostic :

```yaml
current_source: sensor.temperature_primary  # Source actuellement utilisée
source_entities:                             # Liste complète des sources
  - sensor.temperature_primary
  - sensor.temperature_zigbee_backup
  - sensor.temperature_wifi_backup
source_index: 0                              # Index de la source active (0 = primaire)
fallback_count: 3                            # Nombre de basculements depuis le démarrage
last_fallback_time: "2025-11-07T10:30:00"   # Timestamp du dernier basculement
```

## Exemples d'utilisation

### Température avec fallback

```yaml
sensor:
  - platform: fallback_sensors
    name: "Température Maison"
    entities:
      - sensor.temp_thermostat
      - sensor.temp_xiaomi
      - sensor.temp_shelly
```

### Humidité avec fallback

```yaml
sensor:
  - platform: fallback_sensors
    name: "Humidité Salle de bain"
    entities:
      - sensor.humidity_primary
      - sensor.humidity_backup
```

### Consommation énergétique

```yaml
sensor:
  - platform: fallback_sensors
    name: "Consommation Totale"
    entities:
      - sensor.power_meter_zigbee
      - sensor.power_meter_wifi
      - sensor.power_meter_modbus
```

## Automatisations

### Notification lors de basculement

```yaml
automation:
  - alias: "Alerte basculement capteur température"
    trigger:
      - platform: state
        entity_id: sensor.temperature_salon
        attribute: current_source
    condition:
      - condition: template
        value_template: "{{ trigger.from_state.attributes.current_source != trigger.to_state.attributes.current_source }}"
    action:
      - service: notify.mobile_app
        data:
          title: "Capteur température basculé"
          message: >
            Le capteur a basculé de {{ trigger.from_state.attributes.current_source }}
            vers {{ trigger.to_state.attributes.current_source }}
```

### Surveillance du nombre de basculements

```yaml
automation:
  - alias: "Trop de basculements"
    trigger:
      - platform: state
        entity_id: sensor.temperature_salon
        attribute: fallback_count
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.temperature_salon', 'fallback_count') | int > 10 }}"
    action:
      - service: persistent_notification.create
        data:
          title: "Problème de capteur détecté"
          message: >
            Le capteur {{ trigger.entity_id }} a basculé {{ state_attr(trigger.entity_id, 'fallback_count') }} fois.
            Vérifiez vos capteurs sources.
```

## Debugging

Activez les logs de debug dans `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.fallback_sensors: debug
```

Les logs vous indiqueront :
- Quand un capteur change de source
- Quand une source devient indisponible
- Les erreurs de configuration

## Cas d'usage

### Problème : Capteurs Zigbee instables
**Solution** : Utilisez un capteur Wifi comme backup

```yaml
sensor:
  - platform: fallback_sensors
    name: "Température stable"
    entities:
      - sensor.temp_zigbee  # Parfois instable
      - sensor.temp_wifi    # Plus stable mais moins précis
```

### Problème : Maintenance des capteurs
**Solution** : Gardez un capteur de secours pendant le remplacement

```yaml
sensor:
  - platform: fallback_sensors
    name: "Production solaire"
    entities:
      - sensor.solar_new     # Nouveau capteur en test
      - sensor.solar_old     # Ancien capteur fiable
```

### Problème : Différentes sources de données
**Solution** : Priorisez vos sources par fiabilité

```yaml
sensor:
  - platform: fallback_sensors
    name: "Prix électricité"
    entities:
      - sensor.price_api_provider1  # API principale
      - sensor.price_api_provider2  # API de backup
      - sensor.price_static         # Valeur fixe en dernier recours
```

## Limitations et notes

1. **Minimum 2 entités** : La configuration exige au moins 2 entités sources
2. **Pas d'hystérésis** : Le capteur bascule immédiatement (peut être ajouté dans une future version)
3. **Types mixtes** : Vous pouvez mélanger différents types de capteurs, mais c'est à vos risques (ex: température → humidité)
4. **Ordre important** : Les entités sont testées dans l'ordre configuré

## Support et contributions

- **Issues** : [GitHub Issues](https://github.com/yourusername/fallback-sensors/issues)
- **Discussions** : [GitHub Discussions](https://github.com/yourusername/fallback-sensors/discussions)
- **Pull Requests** : Les contributions sont les bienvenues !

## License

MIT License - Voir le fichier LICENSE pour plus de détails

## Changelog

### v1.0.0 (2025-11-07)
- Version initiale
- Fallback séquentiel
- Copie automatique des attributs
- Listeners event-driven
- Attributs de diagnostic
