<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# 🛡️ HA Fall Detector

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.1+-blue?logo=homeassistant)](https://www.home-assistant.io/)
[![Frigate](https://img.shields.io/badge/Frigate-0.13+-green)](https://frigate.video/)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)

**AI-powered fall detection for Home Assistant using your existing Frigate cameras.**

HA Fall Detector watches Frigate camera feeds for human falls using real-time
pose estimation. When a fall is detected and confirmed, it publishes alerts
through MQTT and exposes rich entities in Home Assistant so you can build
automations — push notifications, sirens, lights, or calls for help.

---

> **⚠️ DISCLAIMER**
>
> **This is an assistive monitoring tool, NOT a medical device.** It has not
> been evaluated or certified by any regulatory body (FDA, CE, etc.). False
> negatives (missed falls) and false positives (incorrect alerts) **will**
> occur.
>
> **Do not rely on this software as the sole safety measure for elderly care,
> disability support, or any life-safety application.** Always combine it with
> other safeguards — personal emergency response systems (PERS), regular
> check-ins, professional caregiving, and medical alert devices.
>
> The authors and contributors accept no liability for injuries, harm, or
> damages resulting from the use or misuse of this software. See the
> [LICENSE](LICENSE) for full terms.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Why Two Components?](#why-two-components)
- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Entity Reference](#entity-reference)
- [Service Reference](#service-reference)
- [Event Reference](#event-reference)
- [Example Automations](#example-automations)
- [Hardware Requirements](#hardware-requirements)
- [Privacy](#privacy)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Documentation](#documentation)

---

## Architecture Overview

HA Fall Detector is a **mono-repo** containing two cooperating components that
together provide end-to-end fall detection inside Home Assistant:

```
┌──────────┐    RTSP     ┌──────────────┐   MQTT (events)    ┌─────────────────────┐
│  Camera  │────────────▶│   Frigate    │───────────────────▶│  Fall Detector      │
│  Feed(s) │             │   NVR        │   HTTP (snapshots)  │  Add-on             │
└──────────┘             │              │◀ ─ ─ ─ ─ ─ ─ ─ ─ ─│  (FastAPI container) │
                         └──────────────┘                     │                     │
                                                              │  Detection Pipeline │
                                                              │  ┌───────────────┐  │
                                                              │  │ Person Gate    │  │
                                                              │  │ Pose Estimate  │  │
                                                              │  │ Fall Scoring   │  │
                                                              │  │ Confirmation   │  │
                                                              │  │ Alert Manager  │  │
                                                              │  └───────────────┘  │
                                                              │                     │
                                                              │  MQTT (alerts)      │
                                                              │  HTTP API (status)  │
                                                              └──────────┬──────────┘
                                                                         │
                                                    MQTT alerts ─────────┤
                                                    HTTP polling ────────┤
                                                                         ▼
                                                              ┌─────────────────────┐
                                                              │  HACS Integration   │
                                                              │  (custom component) │
                                                              │                     │
                                                              │  • Binary sensors   │
                                                              │  • Sensors          │
                                                              │  • Switches         │
                                                              │  • Services         │
                                                              │  • Events           │
                                                              └──────────┬──────────┘
                                                                         │
                                                                         ▼
                                                              ┌─────────────────────┐
                                                              │  Home Assistant     │
                                                              │                     │
                                                              │  Automations        │
                                                              │  Dashboards         │
                                                              │  Notifications      │
                                                              │  Scripts            │
                                                              └─────────────────────┘
```

**Data Flow Summary:**

1. **Cameras** stream RTSP video to **Frigate NVR**.
2. **Frigate** runs object detection, publishes `frigate/events` on MQTT when
   a `person` is detected, and exposes snapshot URLs over HTTP.
3. The **Fall Detector Add-on** subscribes to Frigate MQTT events. When a
   person is tracked, it fetches the latest frame and runs the detection
   pipeline: person gate → MoveNet pose estimation → fall scoring →
   confirmation window → alert.
4. Confirmed falls are published to MQTT (`fall_detector/alerts/#`) and
   exposed via a REST API.
5. The **HACS Integration** consumes alerts via MQTT and polls the add-on API
   for status. It creates Home Assistant entities (binary sensors, sensors,
   switches) and fires HA events.
6. Users build **automations** on top of those entities and events.

---

## Why Two Components?

Home Assistant add-ons and custom integrations serve fundamentally different
purposes. Splitting the project gives the best of both worlds:

| Concern | Add-on (container) | Integration (Python component) |
|---|---|---|
| **Heavy computation** | ✅ Runs TensorFlow Lite / MoveNet in its own container with dedicated resources | ❌ HA core is single-threaded asyncio; heavy CPU work would block the event loop |
| **Isolation** | ✅ Crashes don't affect HA core | ❌ A bug in a custom component can crash HA |
| **Dependency freedom** | ✅ Can bundle any native library (OpenCV, TFLite, NumPy) without conflicting with HA's Python environment | ❌ Must use HA's pinned dependency versions |
| **HA entity integration** | ❌ Cannot create HA entities directly | ✅ Native access to HA entity registry, config flows, services, events |
| **User experience** | Configured via add-on options panel | Configured via HA config flow UI |

**In short:** the add-on does the heavy AI lifting; the integration provides
the native Home Assistant experience. They communicate over MQTT and a local
HTTP API.

---

## Features

### Detection

- **Real-time pose estimation** using Google MoveNet (Lightning or Thunder)
- **Multi-stage pipeline** — person gate filters non-person events before
  expensive pose estimation runs
- **Configurable confirmation window** — a single bad frame won't trigger an
  alert; the system requires sustained fall posture over N seconds
- **Per-camera confidence thresholds** — tune sensitivity per camera
- **Zone exclusions** — ignore falls on beds, couches, or other expected
  horizontal surfaces
- **Cooldown timer** — prevent alert storms from the same event

### Alerting

- **MQTT alerts** with structured JSON payloads (camera, confidence, timestamp,
  snapshot path)
- **Mute/unmute per camera** — temporarily suppress alerts without losing
  detection
- **Global mute switch** — disable all alerts system-wide
- **Test alert service** — validate your automation pipeline without a real fall
- **Cooldown management** — automatic cooldown with manual reset option

### Home Assistant Integration

- **Binary sensors** — `fall_detected` per camera (on/off)
- **Sensors** — confidence score, detection count, last event timestamp,
  pipeline latency, system status
- **Switches** — mute per camera, global mute
- **Services** — `test_alert`, `reset_cooldown`, `mute_camera`,
  `unmute_camera`, `clear_alert`
- **Events** — `fall_detector_fall_detected`, `fall_detector_alert_cleared`,
  `fall_detector_system_error`
- **Config flow** — guided setup UI, no YAML required
- **Device grouping** — all entities grouped under a single device per camera

### Operations

- **Health endpoint** — `/api/health` for monitoring
- **Prometheus metrics** — optional `/metrics` endpoint
- **Debug frame logging** — save annotated frames for tuning
- **Structured JSON logging** with configurable log level
- **Graceful shutdown** with in-flight alert completion

---

## Quick Start

### Prerequisites

Before installing HA Fall Detector, you need:

1. **Home Assistant OS** (HAOS) or **Home Assistant Supervised** — add-ons
   require the Supervisor
2. **Frigate NVR** — installed and running with at least one camera configured
   for `person` detection
3. **MQTT Broker** — Mosquitto (the HA add-on works perfectly) with Frigate
   publishing events to it
4. **At least one camera** with a reasonable view of the area to monitor

### Step 1: Install the Fall Detector Add-on

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮** menu (top right) → **Repositories**.
3. Add this repository URL:
   ```
   https://github.com/askb/ha-fall-detector
   ```
4. Find **Fall Detector** in the add-on list and click **Install**.
5. Go to the **Configuration** tab and set:
   ```yaml
   frigate_url: "http://ccab4aaf-frigate:5000"
   mqtt_host: "core-mosquitto"
   mqtt_port: 1883
   mqtt_user: "your_mqtt_user"
   mqtt_password: "your_mqtt_password"
   ```
6. Click **Start**.
7. Check the **Log** tab — you should see:
   ```
   INFO: Fall Detector started successfully
   INFO: Connected to Frigate at http://ccab4aaf-frigate:5000
   INFO: Connected to MQTT broker at core-mosquitto:1883
   INFO: Monitoring cameras: ['front_door', 'living_room', 'hallway']
   ```

### Step 2: Install the HACS Integration

1. Open **HACS** in Home Assistant.
2. Click **⋮** menu → **Custom repositories**.
3. Add:
   - **Repository:** `askb/ha-fall-detector`
   - **Category:** Integration
4. Search for **Fall Detector** and click **Download**.
5. **Restart Home Assistant.**

### Step 3: Configure the Integration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Fall Detector**.
3. Enter the add-on URL (usually `http://homeassistant.local:5000` or the
   add-on ingress URL).
4. The integration will auto-discover your cameras from the add-on.
5. Optionally adjust per-camera settings.

### Step 4: Verify

1. Check **Settings → Devices & Services → Fall Detector** — you should see
   a device per camera.
2. Each device has binary sensors, sensors, and switches.
3. Use the **Developer Tools → Services** panel to call
   `fall_detector.test_alert` with a camera name.
4. Verify you see the binary sensor turn on briefly and then auto-clear.

### Step 5: Build Automations

See [Example Automations](#example-automations) below or the full guide in
[docs/setup.md](docs/setup.md).

---

## Configuration Reference

### Add-on Options

Configure these in the add-on **Configuration** tab:

| Option | Type | Default | Description |
|---|---|---|---|
| `frigate_url` | string | `http://ccab4aaf-frigate:5000` | Frigate HTTP API base URL |
| `mqtt_host` | string | `core-mosquitto` | MQTT broker hostname |
| `mqtt_port` | integer | `1883` | MQTT broker port |
| `mqtt_user` | string | `""` | MQTT username (empty for anonymous) |
| `mqtt_password` | string | `""` | MQTT password |
| `mqtt_topic_prefix` | string | `fall_detector` | Prefix for MQTT topics published by the add-on |
| `frigate_topic_prefix` | string | `frigate` | Frigate's MQTT topic prefix |
| `cameras` | list | `[]` | Camera names to monitor (empty = auto-discover all from Frigate) |
| `confidence_threshold` | float | `0.70` | Global fall confidence threshold (0.0–1.0) |
| `confirmation_seconds` | float | `3.0` | Seconds of sustained fall posture before alerting |
| `cooldown_seconds` | integer | `300` | Seconds between repeated alerts for the same camera |
| `frame_sample_rate` | float | `2.0` | Frames per second to analyze (lower = less CPU) |
| `pose_model` | string | `lightning` | MoveNet model variant: `lightning` (fast) or `thunder` (accurate) |
| `zone_exclusions` | object | `{}` | Per-camera zone names to ignore (see [Tuning](docs/tuning.md)) |
| `debug_frames` | boolean | `false` | Save annotated debug frames to `/share/fall_detector/debug/` |
| `log_level` | string | `info` | Logging level: `debug`, `info`, `warning`, `error` |
| `metrics_enabled` | boolean | `false` | Enable Prometheus metrics endpoint at `/metrics` |

**Example full configuration:**

```yaml
frigate_url: "http://ccab4aaf-frigate:5000"
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_user: "mqtt_user"
mqtt_password: "mqtt_pass"
mqtt_topic_prefix: "fall_detector"
frigate_topic_prefix: "frigate"
cameras:
  - living_room
  - hallway
  - bedroom
confidence_threshold: 0.75
confirmation_seconds: 3.0
cooldown_seconds: 300
frame_sample_rate: 2.0
pose_model: "lightning"
zone_exclusions:
  bedroom: ["bed_zone"]
  living_room: ["couch_zone"]
debug_frames: false
log_level: "info"
metrics_enabled: false
```

### Per-Camera Threshold Overrides

You can override the global confidence threshold per camera in the add-on
configuration:

```yaml
camera_overrides:
  hallway:
    confidence_threshold: 0.85
  bedroom:
    confidence_threshold: 0.65
    confirmation_seconds: 5.0
```

### Integration Options

These are configured through the HA config flow UI:

| Option | Type | Default | Description |
|---|---|---|---|
| Add-on URL | string | auto-detected | HTTP URL of the Fall Detector add-on |
| Poll interval | integer | `30` | Seconds between status polls to the add-on API |
| MQTT discovery | boolean | `true` | Auto-discover cameras from MQTT topics |

---

## Entity Reference

Each monitored camera creates a device with the following entities:

### Binary Sensors

| Entity ID Pattern | Description | On State |
|---|---|---|
| `binary_sensor.fall_detector_{camera}_fall_detected` | Whether a fall is currently detected | Fall confirmed |
| `binary_sensor.fall_detector_{camera}_person_detected` | Whether a person is currently in frame | Person visible |
| `binary_sensor.fall_detector_{camera}_online` | Whether the camera pipeline is active | Pipeline running |

### Sensors

| Entity ID Pattern | Description | Unit |
|---|---|---|
| `sensor.fall_detector_{camera}_confidence` | Confidence score of the latest detection | `%` |
| `sensor.fall_detector_{camera}_detection_count` | Total falls detected since add-on start | count |
| `sensor.fall_detector_{camera}_last_fall` | Timestamp of the last confirmed fall | ISO 8601 |
| `sensor.fall_detector_{camera}_pipeline_latency` | Processing time per frame | `ms` |
| `sensor.fall_detector_system_status` | Overall system status | `healthy` / `degraded` / `error` |

### Switches

| Entity ID Pattern | Description |
|---|---|
| `switch.fall_detector_{camera}_mute` | Mute/unmute alerts for this camera |
| `switch.fall_detector_global_mute` | Mute/unmute all alerts system-wide |

### Diagnostic Sensors

| Entity ID Pattern | Description |
|---|---|
| `sensor.fall_detector_addon_version` | Running add-on version |
| `sensor.fall_detector_uptime` | Add-on uptime |
| `sensor.fall_detector_frames_processed` | Total frames analyzed |

---

## Service Reference

All services are under the `fall_detector` domain.

### `fall_detector.test_alert`

Fire a synthetic fall alert to test your automation pipeline.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `camera` | string | Yes | Camera name to simulate the fall on |
| `confidence` | float | No | Simulated confidence score (default: `0.95`) |

```yaml
service: fall_detector.test_alert
data:
  camera: living_room
  confidence: 0.90
```

### `fall_detector.reset_cooldown`

Reset the alert cooldown timer for a camera, allowing the next detection to
alert immediately.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `camera` | string | Yes | Camera name |

```yaml
service: fall_detector.reset_cooldown
data:
  camera: hallway
```

### `fall_detector.mute_camera`

Mute alerts for a specific camera.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `camera` | string | Yes | Camera name |
| `duration` | integer | No | Auto-unmute after N minutes (default: indefinite) |

```yaml
service: fall_detector.mute_camera
data:
  camera: bedroom
  duration: 60
```

### `fall_detector.unmute_camera`

Unmute alerts for a specific camera.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `camera` | string | Yes | Camera name |

```yaml
service: fall_detector.unmute_camera
data:
  camera: bedroom
```

### `fall_detector.clear_alert`

Manually clear an active fall alert on a camera.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `camera` | string | Yes | Camera name |

```yaml
service: fall_detector.clear_alert
data:
  camera: living_room
```

---

## Event Reference

Events are fired on the Home Assistant event bus. Subscribe in automations
using the `event` trigger platform.

### `fall_detector_fall_detected`

Fired when a fall is confirmed on any camera.

```json
{
  "event_type": "fall_detector_fall_detected",
  "data": {
    "camera": "living_room",
    "confidence": 0.87,
    "timestamp": "2025-01-15T14:32:07.123Z",
    "snapshot_path": "/media/fall_detector/snapshots/living_room_20250115_143207.jpg",
    "pose_keypoints": { "...": "..." },
    "confirmation_duration": 3.2
  }
}
```

### `fall_detector_alert_cleared`

Fired when an active alert is cleared (manually or automatically).

```json
{
  "event_type": "fall_detector_alert_cleared",
  "data": {
    "camera": "living_room",
    "reason": "manual",
    "duration_seconds": 45.2
  }
}
```

### `fall_detector_system_error`

Fired when a system-level error occurs (connection loss, pipeline failure).

```json
{
  "event_type": "fall_detector_system_error",
  "data": {
    "component": "mqtt",
    "error": "Connection lost to broker",
    "timestamp": "2025-01-15T14:35:00.000Z"
  }
}
```

---

## Example Automations

### Push Notification on Fall

```yaml
automation:
  - alias: "Fall Detected - Send Notification"
    trigger:
      - platform: event
        event_type: fall_detector_fall_detected
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "⚠️ Fall Detected!"
          message: >
            Fall detected on {{ trigger.event.data.camera }} camera
            (confidence: {{ (trigger.event.data.confidence * 100) | round }}%).
          data:
            image: "{{ trigger.event.data.snapshot_path }}"
            actions:
              - action: CLEAR_FALL_ALERT
                title: "Clear Alert"
              - action: CALL_EMERGENCY
                title: "Call Emergency"
```

### Flash Lights on Fall

```yaml
automation:
  - alias: "Fall Detected - Flash Lights"
    trigger:
      - platform: state
        entity_id: binary_sensor.fall_detector_living_room_fall_detected
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.living_room
        data:
          flash: long
          color_name: red
```

### Auto-Mute Bedroom at Night

```yaml
automation:
  - alias: "Mute Bedroom Fall Detection at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: fall_detector.mute_camera
        data:
          camera: bedroom
          duration: 480  # 8 hours

  - alias: "Unmute Bedroom Fall Detection in Morning"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: fall_detector.unmute_camera
        data:
          camera: bedroom
```

### Announce Fall on Smart Speaker

```yaml
automation:
  - alias: "Fall Detected - Announce on Speaker"
    trigger:
      - platform: event
        event_type: fall_detector_fall_detected
    condition:
      - condition: state
        entity_id: switch.fall_detector_global_mute
        state: "off"
    action:
      - service: tts.speak
        target:
          entity_id: media_player.living_room_speaker
        data:
          message: >
            Attention! A fall has been detected on the
            {{ trigger.event.data.camera | replace('_', ' ') }} camera.
            Please check on the person immediately.
```

### Log Falls to Logbook

```yaml
automation:
  - alias: "Fall Detected - Log Event"
    trigger:
      - platform: event
        event_type: fall_detector_fall_detected
    action:
      - service: logbook.log
        data:
          name: "Fall Detector"
          message: >
            Fall detected on {{ trigger.event.data.camera }}
            (confidence: {{ (trigger.event.data.confidence * 100) | round }}%)
          entity_id: >
            binary_sensor.fall_detector_{{ trigger.event.data.camera }}_fall_detected
```

---

## Hardware Requirements

### Minimum

| Component | Requirement |
|---|---|
| **Platform** | Raspberry Pi 4 (4 GB+) or equivalent x86_64 |
| **OS** | Home Assistant OS (HAOS) or Supervised |
| **Cameras** | 1–2 cameras with RTSP output |
| **Frigate** | Running with person detection enabled |
| **MQTT** | Mosquitto broker (HA add-on is fine) |

### Recommended

| Component | Recommendation |
|---|---|
| **Platform** | x86_64 mini PC (Intel N100 or better) or RPi 5 |
| **RAM** | 8 GB+ (Frigate + Fall Detector + HA) |
| **Coral TPU** | USB or M.2 — dramatically speeds up Frigate's object detection |
| **Cameras** | 1080p with good low-light performance |
| **Storage** | SSD with 50 GB+ free for snapshots and debug frames |

### CPU Budget Estimates

| Configuration | Per-Camera CPU | Notes |
|---|---|---|
| Lightning model, 2 FPS | ~5–10% of RPi 4 core | Recommended starting point |
| Thunder model, 2 FPS | ~15–25% of RPi 4 core | Better accuracy, higher cost |
| Lightning model, 5 FPS | ~15–20% of RPi 4 core | Faster response, more CPU |
| Thunder model, 5 FPS | ~30–50% of RPi 4 core | Best accuracy, highest cost |

> **Tip:** The Coral TPU benefits **Frigate**, not the Fall Detector directly.
> MoveNet runs on CPU. If you have a capable GPU (e.g., Intel iGPU on an N100),
> future versions may support GPU-accelerated inference.

---

## Privacy

HA Fall Detector is designed with privacy as a core principle:

- **100% local processing** — no frames, video, or detection data ever leave
  your network. There are zero cloud dependencies, zero telemetry, zero
  phone-home behavior.
- **No recording by default** — the add-on processes frames in memory and
  discards them immediately after analysis. Snapshots are only saved when an
  alert fires (for the notification image).
- **Debug frames are opt-in** — annotated frames are only saved to disk when
  you explicitly enable `debug_frames` for tuning purposes.
- **No face recognition** — the system uses skeletal pose estimation only. It
  does not identify **who** fell, only **that** a fall occurred.
- **Camera feeds stay in Frigate** — the add-on never accesses your cameras
  directly. It only receives cropped person snapshots from Frigate's existing
  detection pipeline.
- **You control retention** — configure snapshot retention in Frigate and
  debug frame cleanup in the add-on settings.

For a detailed security analysis, see [docs/threat-model.md](docs/threat-model.md).

---

## Troubleshooting

See the full [Troubleshooting Guide](docs/troubleshooting.md) for detailed
solutions. Quick checks:

1. **Add-on won't start?** Check the add-on logs for startup errors.
2. **No cameras found?** Verify Frigate is running and accessible at the
   configured URL.
3. **Entities show unavailable?** Check the add-on health endpoint and
   verify the integration URL.
4. **Too many false positives?** See the [Tuning Guide](docs/tuning.md).
5. **No alerts received?** Check mute state, cooldown timers, and MQTT
   connectivity.

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development environment setup
- Running tests and linters
- Commit message conventions
- Pull request process

---

## License

Copyright 2025 The Linux Foundation

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the
full text.

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | System design, data flow, component boundaries |
| [Setup Guide](docs/setup.md) | Detailed installation and configuration walkthrough |
| [Tuning Guide](docs/tuning.md) | Reducing false positives, optimizing performance |
| [Threat Model](docs/threat-model.md) | Security analysis, privacy, failure modes |
| [Troubleshooting](docs/troubleshooting.md) | Common problems and solutions |
| [Testing](docs/testing.md) | Running tests, validation checklist |
| [Contributing](CONTRIBUTING.md) | Development setup, code style, PR process |
