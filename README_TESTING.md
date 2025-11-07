# Guide de test avec Docker

Ce guide explique comment tester l'intégration Fallback Sensors localement avec Docker.

## Prérequis

- Docker installé
- Docker Compose installé

## Démarrage rapide

```bash
# 1. Démarrer Home Assistant
docker-compose up -d

# 2. Suivre les logs
docker-compose logs -f homeassistant

# 3. Accéder à Home Assistant
# Ouvrir http://localhost:8123
# Premier démarrage : créer un compte utilisateur
```

## Configuration de test

### Capteurs simulés

L'environnement de test inclut 3 capteurs de température simulés :
- `sensor.test_temp_primary` : Capteur principal (20-25°C)
- `sensor.test_temp_backup` : Capteur de secours (18-21°C)
- `sensor.test_temp_fallback` : Capteur de fallback (22-24°C)

### Capteur Fallback configuré

Un capteur fallback est pré-configuré dans `test-config/configuration.yaml` :
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

## Tests manuels

### Test 1 : Configuration via UI

1. **Paramètres** → **Appareils et services**
2. **Ajouter une intégration**
3. Rechercher **"Fallback Sensors"**
4. Configurer :
   - Nom : "Mon capteur de test"
   - Entités : sélectionner 2+ capteurs
   - Hystérésis : 10 secondes
5. Vérifier que le capteur apparaît dans **États**

### Test 2 : Fallback automatique

1. Aller dans **Outils de développement** → **États**
2. Observer l'état de `sensor.temperature_fallback_test`
3. Attributs à vérifier :
   - `current_source` : doit être `sensor.test_temp_primary`
   - `source_index` : doit être `0`
   - `fallback_count` : doit être `0` au début

### Test 3 : Simuler une panne

Pour simuler une panne du capteur principal, modifier le fichier `test-config/configuration.yaml` et forcer un état unavailable (nécessite un restart).

Ou via les outils de développement :
1. **Outils de développement** → **États**
2. Trouver `sensor.test_temp_primary`
3. Modifier l'état temporairement (ne persiste pas)

### Test 4 : Hystérésis

1. Observer le capteur fallback
2. Désactiver temporairement le capteur principal
3. Le capteur fallback devrait attendre 5 secondes avant de basculer
4. Vérifier les logs : `docker-compose logs -f homeassistant | grep fallback`

### Test 5 : Conditions personnalisées

Le capteur de test a une condition `range: 15-30°C`.

Pour tester :
1. Modifier `test-config/configuration.yaml`
2. Changer la valeur d'un capteur pour qu'elle soit hors de la plage
3. Redémarrer : `docker-compose restart`
4. Observer que le capteur est ignoré

## Vérification des logs

```bash
# Logs en temps réel
docker-compose logs -f homeassistant

# Filtrer uniquement fallback_sensors
docker-compose logs -f homeassistant | grep fallback_sensors

# Logs complets
docker-compose logs homeassistant
```

Logs attendus :
```
DEBUG (MainThread) [custom_components.fallback_sensors] Setting up fallback sensor 'Temperature Fallback Test'
INFO (MainThread) [custom_components.fallback_sensors.sensor] Fallback sensor 'Temperature Fallback Test' switched to 'sensor.test_temp_primary'
```

## Modifications en temps réel

L'intégration est montée en lecture seule depuis le code source :
```yaml
volumes:
  - ./custom_components/fallback_sensors:/config/custom_components/fallback_sensors:ro
```

Pour tester des modifications :
1. Modifier le code dans `custom_components/fallback_sensors/`
2. Redémarrer le container : `docker-compose restart`
3. Les changements sont immédiatement pris en compte

## Nettoyage

```bash
# Arrêter Home Assistant
docker-compose down

# Supprimer les données de test (base de données, logs, etc.)
rm -rf test-config/.storage test-config/*.db* test-config/*.log

# Redémarrer propre
docker-compose up -d
```

## Débogage

### Home Assistant ne démarre pas

```bash
# Vérifier les logs
docker-compose logs homeassistant

# Vérifier la configuration
docker-compose exec homeassistant python -m homeassistant --script check_config -c /config
```

### L'intégration n'apparaît pas

1. Vérifier que le dossier est bien monté :
   ```bash
   docker-compose exec homeassistant ls -la /config/custom_components/fallback_sensors
   ```

2. Vérifier le manifest.json :
   ```bash
   docker-compose exec homeassistant cat /config/custom_components/fallback_sensors/manifest.json
   ```

3. Redémarrer :
   ```bash
   docker-compose restart
   ```

### Erreurs Python

```bash
# Shell interactif dans le container
docker-compose exec homeassistant bash

# Tester l'import Python
python3 -c "from custom_components.fallback_sensors.sensor import FallbackSensor; print('OK')"
```

## Accès aux fichiers de configuration

Les fichiers de configuration sont dans `test-config/` :
- `configuration.yaml` : Configuration principale
- `automations.yaml` : Automatisations
- `scripts.yaml` : Scripts
- `scenes.yaml` : Scènes

Modifier ces fichiers et redémarrer pour tester différentes configurations.

## Interface Web

Home Assistant est accessible sur : **http://localhost:8123**

Lors du premier démarrage :
1. Créer un compte utilisateur
2. Configurer nom et localisation
3. Accepter les paramètres par défaut

## Tests avancés

### Test des conditions regex

Ajouter dans `test-config/configuration.yaml` :
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

### Test du fallback_count

Créer une automatisation qui compte les basculements :
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
          title: "Fallback détecté"
          message: "Le capteur a basculé {{ trigger.to_state.attributes.fallback_count }} fois"
```

## Commandes utiles

```bash
# Démarrer en arrière-plan
docker-compose up -d

# Arrêter
docker-compose down

# Redémarrer
docker-compose restart

# Voir les logs
docker-compose logs -f

# Shell dans le container
docker-compose exec homeassistant bash

# Rebuilder l'image
docker-compose pull
docker-compose up -d --force-recreate
```
