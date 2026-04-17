<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Setup Guide

This guide walks you through installing and configuring HA Fall Detector from
scratch. By the end, you will have fall detection running on your cameras with
alerts flowing into Home Assistant.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Install the Fall Detector Add-on](#step-1-install-the-fall-detector-add-on)
- [Step 2: Install the HACS Integration](#step-2-install-the-hacs-integration)
- [Step 3: Configure the Integration](#step-3-configure-the-integration)
- [Step 4: Verify Everything Works](#step-4-verify-everything-works)
- [Step 5: Set Up Automations](#step-5-set-up-automations)
- [Frigate Configuration Requirements](#frigate-configuration-requirements)
- [MQTT Broker Requirements](#mqtt-broker-requirements)
- [Upgrading](#upgrading)
- [Uninstalling](#uninstalling)

---

## Prerequisites

Before you begin, ensure you have all of the following in place:

### Home Assistant

- **Home Assistant OS** (HAOS) or **Home Assistant Supervised** installation.
  - Add-ons require the HA Supervisor. Container and Core installations do
    not support add-ons.
- **Version**: Home Assistant 2024.1 or newer.
- **HACS** (Home Assistant Community Store) installed.
  - If you don't have HACS, install it first:
    [hacs.xyz/docs/use/download/download](https://hacs.xyz/docs/use/download/download/)

### Frigate NVR

- **Frigate** installed and running (as an HA add-on or standalone).
  - Version 0.13 or newer recommended.
- **At least one camera** configured in Frigate with `person` detection
  enabled.
- Frigate must be publishing events to your MQTT broker.
- Frigate's HTTP API must be accessible from the Fall Detector add-on.

### MQTT Broker

- An MQTT broker running and accessible.
  - The **Mosquitto** HA add-on is the easiest option.
- Frigate must be configured to use this broker.
- You need the broker hostname, port, and credentials (if authentication is
  enabled).

### Hardware

- See the [Hardware Requirements](../README.md#hardware-requirements) section
  in the README for minimum and recommended specs.

---

## Step 1: Install the Fall Detector Add-on

### Add the Repository

1. In Home Assistant, navigate to **Settings → Add-ons**.
2. Click the **Add-on Store** button (bottom right).
3. Click the **⋮** overflow menu (top right) → **Repositories**.
4. Paste the repository URL:
   ```
   https://github.com/askb/ha-fall-detector
   ```
5. Click **Add** → **Close**.

### Install the Add-on

1. The Fall Detector add-on should now appear in the store. If not, refresh
   the page.
2. Click **Fall Detector**.
3. Click **Install**. This downloads the Docker image and may take a few
   minutes.

### Configure the Add-on

1. Go to the **Configuration** tab.
2. Set the required options:

```yaml
# Required: Frigate connection
frigate_url: "http://ccab4aaf-frigate:5000"

# Required: MQTT broker connection
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_user: "your_mqtt_user"
mqtt_password: "your_mqtt_password"
```

**Finding your Frigate URL:**

- If Frigate is an HA add-on: `http://ccab4aaf-frigate:5000` (the default
  add-on hostname).
- If Frigate is standalone: use its IP address and port, e.g.,
  `http://192.168.1.100:5000`.
- To find the Frigate add-on hostname:
  1. Go to **Settings → Add-ons → Frigate**.
  2. Check the **Info** tab for the hostname.

**Finding your MQTT broker:**

- If using the Mosquitto HA add-on: host is `core-mosquitto`, port is `1883`.
- If using an external broker: use its IP address and port.
- MQTT credentials: the same user/password you configured for Frigate.

3. Optionally configure advanced settings:

```yaml
# Camera selection (empty = auto-discover from Frigate)
cameras: []

# Detection tuning
confidence_threshold: 0.70
confirmation_seconds: 3.0
cooldown_seconds: 300
frame_sample_rate: 2.0
pose_model: "lightning"

# Zone exclusions
zone_exclusions:
  bedroom: ["bed_zone"]

# Debugging
debug_frames: false
log_level: "info"
```

4. Click **Save**.

### Start the Add-on

1. Go to the **Info** tab.
2. Optionally enable **Start on boot** and **Watchdog**.
3. Click **Start**.
4. Go to the **Log** tab and verify successful startup:

```
INFO: Fall Detector v1.0.0 starting...
INFO: Loading MoveNet Lightning model...
INFO: Model loaded in 2.3s
INFO: Connecting to MQTT broker at core-mosquitto:1883...
INFO: MQTT connected successfully
INFO: Connecting to Frigate at http://ccab4aaf-frigate:5000...
INFO: Frigate connected - found 3 cameras: front_door, living_room, hallway
INFO: Subscribing to frigate/events...
INFO: FastAPI server started on port 5000
INFO: Fall Detector ready - monitoring 3 cameras
```

**If you see errors**, check the [Troubleshooting Guide](troubleshooting.md).

---

## Step 2: Install the HACS Integration

### Add the Custom Repository

1. Open **HACS** in the Home Assistant sidebar.
2. Click the **⋮** overflow menu (top right) → **Custom repositories**.
3. Fill in:
   - **Repository URL:** `askb/ha-fall-detector`
   - **Category:** Integration
4. Click **Add**.

### Download the Integration

1. In HACS, go to **Integrations**.
2. Click **+ Explore & Download Repositories**.
3. Search for **Fall Detector**.
4. Click on it → click **Download**.
5. Select the latest version → **Download**.

### Restart Home Assistant

1. Go to **Settings → System → Restart**.
2. Click **Restart** and wait for HA to come back online.

> **Important:** The integration will not appear in the integration list until
> after a restart.

---

## Step 3: Configure the Integration

### Add the Integration

1. Go to **Settings → Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Fall Detector**.
4. Click on it.

### Config Flow

The integration presents a guided setup:

#### Screen 1: Connection

| Field | Value | Notes |
|---|---|---|
| **Add-on URL** | `http://homeassistant.local:5000` | Auto-detected if add-on is running |
| **Poll interval** | `30` | Seconds between status polls |

- If the add-on is running on the same HAOS instance, the URL is
  auto-detected.
- Click **Submit**.

#### Screen 2: Cameras

- The integration queries the add-on for available cameras.
- A list of discovered cameras is shown with checkboxes.
- Select the cameras you want to create entities for.
- Click **Submit**.

#### Screen 3: Confirmation

- Summary of configuration is shown.
- Click **Finish**.

### Post-Configuration

After setup, you should see:

1. **Devices & Services → Fall Detector** shows as configured.
2. One **device** per monitored camera.
3. Each device contains binary sensors, sensors, and switches.

### Reconfiguring

To change settings later:

1. Go to **Settings → Devices & Services → Fall Detector**.
2. Click **Configure**.
3. Modify settings → **Submit**.

---

## Step 4: Verify Everything Works

### Check Entity Status

1. Go to **Settings → Devices & Services → Fall Detector**.
2. Click on a camera device.
3. Verify all entities show valid states (not `unavailable` or `unknown`):
   - `binary_sensor.fall_detector_{camera}_fall_detected` → `off`
   - `binary_sensor.fall_detector_{camera}_person_detected` → depends on
     whether someone is in view
   - `binary_sensor.fall_detector_{camera}_online` → `on`
   - `sensor.fall_detector_{camera}_confidence` → `0`
   - `sensor.fall_detector_system_status` → `healthy`

### Test Alert

1. Go to **Developer Tools → Services**.
2. Select `fall_detector.test_alert`.
3. Fill in:
   ```yaml
   camera: living_room
   confidence: 0.90
   ```
4. Click **Call Service**.
5. Verify:
   - `binary_sensor.fall_detector_living_room_fall_detected` turns `on`
     briefly.
   - `sensor.fall_detector_living_room_confidence` shows `90`.
   - The alert auto-clears after a few seconds.

### Check Add-on Health

1. Open a browser and navigate to:
   ```
   http://homeassistant.local:5000/api/health
   ```
   Or use the add-on's **Web UI** link if enabled.
2. You should see a JSON response:
   ```json
   {
     "status": "healthy",
     "version": "1.0.0",
     "cameras": 3,
     "mqtt_connected": true,
     "frigate_connected": true
   }
   ```

### Verify MQTT Flow

1. Use an MQTT client (e.g., MQTT Explorer) to subscribe to
   `fall_detector/#`.
2. You should see periodic status messages on `fall_detector/status`.
3. After a test alert, you should see a message on
   `fall_detector/alerts/{camera}`.

---

## Step 5: Set Up Automations

With everything verified, create automations to respond to fall detections.
See the [Example Automations](../README.md#example-automations) section in
the README for ready-to-use templates.

Common automation patterns:

### Push Notification

The most common use case — send an immediate notification to your phone:

1. Go to **Settings → Automations & Scenes → Create Automation**.
2. **Trigger**: Event → `fall_detector_fall_detected`
3. **Action**: Notify → your mobile device
4. Include the camera name and snapshot in the notification.

### Multi-Action Response

Combine multiple actions for a comprehensive response:

1. Send push notification with snapshot
2. Flash lights red in the affected room
3. Announce on smart speakers
4. Start recording the camera (via Frigate)

### Scheduled Muting

If certain cameras should be muted at specific times (e.g., bedroom at night):

1. Time trigger at bedtime → call `fall_detector.mute_camera`
2. Time trigger in the morning → call `fall_detector.unmute_camera`

See the [Tuning Guide](tuning.md) for guidance on optimizing detection
quality before relying on automations.

---

## Frigate Configuration Requirements

The Fall Detector depends on Frigate for camera feeds and person detection.
Your Frigate configuration must meet these requirements:

### Person Detection Enabled

Each camera you want to monitor must have `person` detection enabled in
Frigate:

```yaml
# frigate.yml
cameras:
  living_room:
    ffmpeg:
      inputs:
        - path: rtsp://user:pass@camera-ip:554/stream
          roles:
            - detect
    detect:
      enabled: true
      width: 1280
      height: 720
      fps: 5
    objects:
      track:
        - person  # Required — must include 'person'
    snapshots:
      enabled: true  # Required for frame fetching
```

### MQTT Publishing

Frigate must publish events to MQTT:

```yaml
# frigate.yml
mqtt:
  enabled: true
  host: core-mosquitto  # Your MQTT broker
  port: 1883
  user: mqtt_user
  password: mqtt_pass
  topic_prefix: frigate  # Must match fall_detector's frigate_topic_prefix
```

### Snapshots

Frigate must have snapshots enabled (globally or per camera) so the Fall
Detector can fetch frames via HTTP:

```yaml
# frigate.yml - global or per camera
snapshots:
  enabled: true
  retain:
    default: 7  # Days to retain
```

### Zones (Optional)

If you want to exclude specific areas (beds, couches), define zones in
Frigate:

```yaml
# frigate.yml
cameras:
  bedroom:
    zones:
      bed_zone:
        coordinates: 0.1,0.5,0.6,0.5,0.6,0.9,0.1,0.9
```

Then add the zone to `zone_exclusions` in the Fall Detector configuration:

```yaml
zone_exclusions:
  bedroom: ["bed_zone"]
```

---

## MQTT Broker Requirements

### Mosquitto HA Add-on (Recommended)

If using the Mosquitto HA add-on:

1. Install from the Add-on Store if not already installed.
2. Create a user for Fall Detector (or use an existing one):
   - Go to **Settings → People → Users → Add User**.
   - Or configure directly in the Mosquitto add-on config.
3. Note the credentials — use them in the Fall Detector add-on configuration.

### External Broker

If using an external MQTT broker:

- Ensure the broker is reachable from the HA host.
- The Fall Detector add-on needs to publish and subscribe to topics.
- No special broker configuration is required beyond standard authentication.

### Required Capabilities

- **QoS 0 and 1** support (standard).
- **Retained messages** support (for availability topics).
- **Wildcard subscriptions** (`#` and `+`) support.
- **No TLS required** for local communication (but recommended if crossing
  network boundaries — see [Threat Model](threat-model.md)).

---

## Upgrading

### Add-on Upgrade

1. Go to **Settings → Add-ons → Fall Detector**.
2. If an update is available, click **Update**.
3. The add-on will restart automatically.
4. Check the **Log** tab for successful startup.

### Integration Upgrade

1. Open **HACS → Integrations → Fall Detector**.
2. If an update is available, click **Update**.
3. **Restart Home Assistant**.
4. The integration will re-initialize with the existing configuration.

### Breaking Changes

Major version upgrades may include breaking changes. Always check the
[CHANGELOG](../CHANGELOG.md) before upgrading. If a configuration migration
is needed, release notes will include instructions.

---

## Uninstalling

### Remove the Integration

1. Go to **Settings → Devices & Services → Fall Detector**.
2. Click **⋮** → **Delete**.
3. All entities, devices, and services will be removed.

### Remove the Add-on

1. Go to **Settings → Add-ons → Fall Detector**.
2. Click **Uninstall**.

### Remove HACS Custom Repository

1. Open **HACS → Integrations**.
2. Find **Fall Detector** → click **⋮** → **Remove**.

### Clean Up

Optionally remove snapshots and debug frames:

```
/share/fall_detector/
```

This directory can be safely deleted after uninstalling.
