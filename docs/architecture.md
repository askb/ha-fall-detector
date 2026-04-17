<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Architecture

This document describes the system architecture of HA Fall Detector, including
component responsibilities, data flow, API contracts, and design decisions.

---

## Table of Contents

- [System Overview](#system-overview)
- [Component Diagram](#component-diagram)
- [Data Flow](#data-flow)
- [Detection Pipeline](#detection-pipeline)
- [Why Split Into Add-on + Integration?](#why-split-into-add-on--integration)
- [Component Responsibility Boundaries](#component-responsibility-boundaries)
- [API Contract](#api-contract)
- [MQTT Topic Layout](#mqtt-topic-layout)
- [Storage and State Management](#storage-and-state-management)
- [Threading and Async Model](#threading-and-async-model)

---

## System Overview

HA Fall Detector consists of two cooperating components that bridge the gap
between heavy AI inference and native Home Assistant entity management:

1. **Fall Detector Add-on** (`addon/fall_detector/`) — A Docker container
   running a FastAPI application that performs the AI fall detection pipeline.
2. **HACS Integration** (`custom_components/fall_detector/`) — A Home
   Assistant custom component that exposes detection results as native HA
   entities, services, and events.

The add-on handles all computationally intensive work (image processing, pose
estimation, scoring) in an isolated container. The integration handles all HA
interactions (entity creation, config flow, service registration, event
firing). They communicate over MQTT (real-time alerts) and HTTP (status
polling).

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Home Assistant OS (HAOS)                         │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Home Assistant Core                             │  │
│  │                                                                   │  │
│  │  ┌─────────────────────────────────────┐                          │  │
│  │  │  HACS Integration                   │                          │  │
│  │  │  custom_components/fall_detector/   │                          │  │
│  │  │                                     │                          │  │
│  │  │  ┌─────────────┐ ┌──────────────┐  │  ┌────────────────────┐  │  │
│  │  │  │ Coordinator │ │ Config Flow  │  │  │  Automations       │  │  │
│  │  │  │ (poll/MQTT) │ │              │  │  │  Scripts            │  │  │
│  │  │  └──────┬──────┘ └──────────────┘  │  │  Dashboards        │  │  │
│  │  │         │                           │  └────────────────────┘  │  │
│  │  │  ┌──────┴──────────────────┐        │           ▲              │  │
│  │  │  │ Entities                │        │           │              │  │
│  │  │  │ • binary_sensor.*      │────────────────────┘              │  │
│  │  │  │ • sensor.*             │        │                          │  │
│  │  │  │ • switch.*             │        │                          │  │
│  │  │  │ • Services             │        │                          │  │
│  │  │  │ • Events               │        │                          │  │
│  │  │  └─────────────────────────┘        │                          │  │
│  │  └──────────────┬──────────────────────┘                          │  │
│  │                 │  ▲                                               │  │
│  └─────────────────┼──┼─────────────────────────────────────────────┘  │
│                    │  │  HTTP (poll /api/status)                        │
│     MQTT           │  │  MQTT (subscribe fall_detector/alerts/#)       │
│     (subscribe)    │  │                                                │
│                    ▼  │                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Fall Detector Add-on                          │   │
│  │                    (Docker container)                            │   │
│  │                                                                 │   │
│  │  ┌──────────┐  ┌────────────────┐  ┌──────────────────────┐    │   │
│  │  │ FastAPI  │  │ MQTT Client    │  │ Detection Pipeline   │    │   │
│  │  │ Server   │  │                │  │                      │    │   │
│  │  │          │  │ Subscribe:     │  │ 1. Person Gate       │    │   │
│  │  │ /api/*   │  │  frigate/+     │  │ 2. Frame Fetch       │    │   │
│  │  │ /health  │  │                │  │ 3. Pose Estimation   │    │   │
│  │  │ /metrics │  │ Publish:       │  │ 4. Fall Scoring      │    │   │
│  │  │          │  │  fall_detector │  │ 5. Confirmation      │    │   │
│  │  └──────────┘  │  /alerts/#    │  │ 6. Alert Manager     │    │   │
│  │                │               │  └──────────────────────┘    │   │
│  │                └───────────────┘                               │   │
│  └────────────────────────┬────────────────────────────────────────┘   │
│                           │  MQTT (subscribe frigate/events)           │
│                           │  HTTP (fetch snapshots)                    │
│                           ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Frigate NVR Add-on                            │   │
│  │                                                                 │   │
│  │  • Object detection (person, car, etc.)                         │   │
│  │  • RTSP stream processing                                      │   │
│  │  • Snapshot API                                                 │   │
│  │  • Event MQTT publishing                                       │   │
│  └────────────────────────┬────────────────────────────────────────┘   │
│                           │  RTSP                                      │
│                           ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  IP Cameras (RTSP)                                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Mosquitto MQTT Broker                                          │   │
│  │  (shared by Frigate, Fall Detector, and Home Assistant)         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

The complete data flow from camera to user notification:

### 1. Camera → Frigate (continuous)

- Cameras stream RTSP video to Frigate NVR.
- Frigate runs its own object detection model (SSD MobileNet, YOLO, etc.).
- When Frigate detects a `person` object, it publishes an event to MQTT.

### 2. Frigate → Add-on: MQTT Event (real-time)

- The add-on subscribes to `frigate/events` on MQTT.
- Frigate publishes JSON events containing:
  - Event type (`new`, `update`, `end`)
  - Camera name
  - Object label (`person`)
  - Bounding box coordinates
  - Object tracking ID
  - Snapshot availability

### 3. Add-on: Person Gate (filtering)

- The add-on's **person gate** filters incoming events:
  - Discard non-`person` events immediately.
  - Discard events from cameras not in the monitored list.
  - Discard events from excluded zones.
  - Rate-limit frame fetches to `frame_sample_rate` per second.
- Only events passing all gates proceed to pose estimation.

### 4. Add-on: Frame Fetch (HTTP)

- For events that pass the person gate, the add-on fetches the latest
  snapshot from Frigate's HTTP API:
  ```
  GET {frigate_url}/api/{camera}/latest.jpg?bbox=1&h=480
  ```
- The snapshot is cropped to the person bounding box region (with padding)
  using the coordinates from the MQTT event.

### 5. Add-on: Pose Estimation

- The cropped frame is fed into the **MoveNet** TensorFlow Lite model.
- MoveNet outputs 17 body keypoints with confidence scores:
  - Nose, left/right eye, left/right ear
  - Left/right shoulder, left/right elbow, left/right wrist
  - Left/right hip, left/right knee, left/right ankle
- Each keypoint has (x, y, confidence) values.

### 6. Add-on: Fall Scoring

- The fall scoring algorithm analyzes the pose keypoints:
  - **Torso angle** — angle of the line from hip midpoint to shoulder
    midpoint relative to vertical. A near-horizontal torso indicates a fall.
  - **Hip-to-shoulder vertical distance** — compressed distance suggests a
    horizontal body.
  - **Keypoint clustering** — all keypoints at similar y-coordinates
    suggests a horizontal body.
  - **Leg-hip relationship** — legs at the same height as hips suggests
    lying down rather than standing.
- These features are combined into a single confidence score (0.0–1.0).

### 7. Add-on: Confirmation Window

- A single frame with a high fall score does **not** immediately trigger an
  alert.
- The confirmation stage requires the fall score to exceed the threshold for
  `confirmation_seconds` consecutive seconds.
- This dramatically reduces false positives from momentary poses (bending
  to tie shoes, playing with pets, yoga poses).
- The confirmation state machine per camera:
  ```
  IDLE → CANDIDATE → CONFIRMING → CONFIRMED → COOLDOWN → IDLE
  ```

### 8. Add-on: Alert Manager

- When a fall is confirmed, the Alert Manager:
  1. Publishes an alert to MQTT: `fall_detector/alerts/{camera}`
  2. Saves a snapshot to `/share/fall_detector/snapshots/`
  3. Updates the internal state (for API consumers)
  4. Starts the cooldown timer for that camera
- The MQTT alert payload:
  ```json
  {
    "camera": "living_room",
    "confidence": 0.87,
    "timestamp": "2025-01-15T14:32:07.123Z",
    "snapshot_path": "/share/fall_detector/snapshots/living_room_20250115_143207.jpg",
    "event_id": "abc123",
    "pose_keypoints": { ... },
    "confirmation_duration": 3.2
  }
  ```

### 9. Add-on → Integration: MQTT + HTTP

- The HACS integration receives alerts in two ways:
  - **MQTT subscription** — `fall_detector/alerts/#` for real-time alerts
    (low latency, event-driven).
  - **HTTP polling** — `GET /api/status` every N seconds for overall system
    state, camera statuses, and detection counts (reliable, catches anything
    MQTT might have missed).
- Using both ensures no alerts are lost if MQTT has a momentary disconnect.

### 10. Integration → Home Assistant Entities

- The integration updates HA entities based on received data:
  - `binary_sensor.fall_detector_{camera}_fall_detected` → `on`
  - `sensor.fall_detector_{camera}_confidence` → `0.87`
  - `sensor.fall_detector_{camera}_last_fall` → timestamp
  - `sensor.fall_detector_{camera}_detection_count` → incremented
- Fires `fall_detector_fall_detected` event on the HA event bus.

### 11. Home Assistant → User

- Users build automations triggered by the entities/events.
- Notifications, lights, sirens, TTS announcements, etc.

---

## Detection Pipeline

The detection pipeline runs as an async task inside the add-on. Here is the
detailed sequence for a single person detection:

```
Frigate MQTT Event (person detected)
         │
         ▼
┌─────────────────┐
│  Person Gate    │──── Not a person? ──── DISCARD
│                 │──── Wrong camera? ──── DISCARD
│                 │──── Excluded zone? ─── DISCARD
│                 │──── Rate limited? ──── DISCARD
└────────┬────────┘
         │ Pass
         ▼
┌─────────────────┐
│  Frame Fetch    │──── HTTP GET from Frigate
│                 │──── Crop to bounding box
│                 │──── Resize to model input (192x192 or 256x256)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Pose Estimate  │──── Run MoveNet TFLite inference
│                 │──── Extract 17 keypoints
│                 │──── Validate keypoint confidence (min 3 visible)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fall Scoring   │──── Compute torso angle
│                 │──── Compute vertical compression
│                 │──── Compute keypoint clustering
│                 │──── Weighted combination → score (0.0–1.0)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Confirmation   │──── score < threshold? ──── Reset timer → IDLE
│  State Machine  │──── score >= threshold?
│                 │     ├── First frame? ──── Start timer → CANDIDATE
│                 │     ├── Timer < N sec? ── Continue → CONFIRMING
│                 │     └── Timer >= N sec? ─ CONFIRMED ──┐
└─────────────────┘                                       │
                                                          ▼
                                                ┌─────────────────┐
                                                │  Alert Manager  │
                                                │                 │
                                                │  1. Check mute  │
                                                │  2. Check cool  │
                                                │  3. Save snap   │
                                                │  4. Publish MQTT│
                                                │  5. Update state│
                                                │  6. Start cool  │
                                                └─────────────────┘
```

### Pipeline Stages in Detail

#### Person Gate

The person gate is a lightweight filter that runs on every Frigate event. Its
purpose is to avoid expensive pose estimation on irrelevant events.

- **Object filter**: Only `person` objects proceed.
- **Camera filter**: Only configured/discovered cameras proceed.
- **Zone filter**: Events in excluded zones are discarded.
- **Rate limiter**: A token bucket per camera limits frame fetches to
  `frame_sample_rate` FPS. Events arriving faster than the rate are silently
  discarded.
- **Tracking filter**: Only `new` and `update` events are processed. `end`
  events reset the confirmation state for that tracking ID.

#### Pose Estimation

- Model: Google MoveNet SinglePose (Lightning or Thunder variant).
- Input: 192×192 (Lightning) or 256×256 (Thunder) resized RGB image.
- Output: 17 keypoints, each with (y, x, confidence) normalized to [0, 1].
- Runtime: TensorFlow Lite with XNNPACK delegate for CPU optimization.
- Latency: ~15 ms (Lightning on x86) to ~50 ms (Thunder on RPi 4).

#### Fall Scoring

The scoring algorithm combines multiple geometric features:

| Feature | Weight | Description |
|---|---|---|
| Torso angle | 0.40 | Angle of shoulder-midpoint to hip-midpoint vs vertical |
| Vertical compression | 0.25 | Ratio of body vertical extent to expected standing height |
| Keypoint y-variance | 0.20 | Low variance = all keypoints at same height = horizontal |
| Leg-hip delta | 0.15 | Difference between hip y and ankle y coordinates |

Final score = weighted sum, clamped to [0.0, 1.0].

#### Confirmation State Machine

Each camera maintains an independent state machine:

| State | Description | Transition |
|---|---|---|
| `IDLE` | No fall candidate | Score >= threshold → `CANDIDATE` |
| `CANDIDATE` | First high-score frame seen | Timer started |
| `CONFIRMING` | Sustained high scores | Score < threshold → `IDLE`; Timer expires → `CONFIRMED` |
| `CONFIRMED` | Fall alert fired | Alert published → `COOLDOWN` |
| `COOLDOWN` | Suppressing repeat alerts | Timer expires → `IDLE`; Manual reset → `IDLE` |

---

## Why Split Into Add-on + Integration?

### The Problem

Home Assistant's architecture creates a tension between heavy computation and
native integration:

- **Custom components** run inside HA Core's Python process. They share the
  asyncio event loop. Long-running synchronous tasks (like TFLite inference)
  block the entire event loop, making HA unresponsive.
- **Add-ons** run in isolated Docker containers with their own resources. They
  can bundle any native libraries. But they cannot create HA entities or
  participate in the entity registry.

### The Solution

Split the system along the computation/integration boundary:

| Layer | Component | Reason |
|---|---|---|
| AI inference | Add-on | Needs TFLite, NumPy, OpenCV; CPU-intensive; must not block HA |
| Alert logic | Add-on | Confirmation windows, cooldowns, mute state — tightly coupled to inference |
| MQTT I/O | Add-on | Direct MQTT subscription to Frigate events; pub/sub for alerts |
| HA entities | Integration | Only custom components can create entities |
| Config flow | Integration | Only custom components can use HA's config flow UI |
| Services | Integration | Only custom components can register HA services |
| Events | Integration | Only custom components can fire HA events |

### Communication Contract

The two components communicate over:

1. **MQTT** — for real-time alerts (add-on publishes → integration subscribes)
2. **HTTP API** — for status polling (integration polls → add-on serves)

This is a clean, well-defined boundary that can be independently tested.

---

## Component Responsibility Boundaries

### Add-on Owns

- Frigate MQTT event processing
- Frame fetching and preprocessing
- MoveNet model loading and inference
- Fall scoring algorithm
- Confirmation state machine
- Alert cooldown management
- Mute state management
- MQTT alert publishing
- Snapshot saving
- Health and metrics endpoints
- Debug frame logging

### Integration Owns

- HA config flow (setup UI)
- Entity creation and lifecycle
- Entity state updates
- HA service registration
- HA event firing
- MQTT alert subscription (within HA)
- HTTP status polling
- Device registry management
- Diagnostics data collection

### Shared (Contract)

- MQTT topic schema
- HTTP API schema
- Alert payload format
- Status response format

---

## API Contract

### HTTP API (Add-on → Integration)

The add-on exposes a FastAPI server (default port 5000) with the following
endpoints:

#### `GET /api/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "cameras": 3,
  "mqtt_connected": true,
  "frigate_connected": true
}
```

#### `GET /api/status`

Full system status, polled by the integration.

**Response:**
```json
{
  "system": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 3600,
    "frames_processed": 12500,
    "pose_model": "lightning"
  },
  "cameras": {
    "living_room": {
      "online": true,
      "fall_detected": false,
      "person_detected": true,
      "muted": false,
      "confidence": 0.0,
      "detection_count": 2,
      "last_fall": "2025-01-15T14:32:07.123Z",
      "pipeline_latency_ms": 23,
      "state": "IDLE",
      "cooldown_remaining_seconds": 0
    },
    "hallway": {
      "online": true,
      "fall_detected": false,
      "person_detected": false,
      "muted": false,
      "confidence": 0.0,
      "detection_count": 0,
      "last_fall": null,
      "pipeline_latency_ms": 0,
      "state": "IDLE",
      "cooldown_remaining_seconds": 0
    }
  }
}
```

#### `POST /api/test_alert`

Trigger a synthetic alert for testing.

**Request:**
```json
{
  "camera": "living_room",
  "confidence": 0.95
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Test alert published for living_room"
}
```

#### `POST /api/mute/{camera}`

Mute alerts for a camera.

**Request (optional body):**
```json
{
  "duration_minutes": 60
}
```

#### `POST /api/unmute/{camera}`

Unmute alerts for a camera.

#### `POST /api/reset_cooldown/{camera}`

Reset the cooldown timer for a camera.

#### `POST /api/clear_alert/{camera}`

Clear an active alert for a camera.

#### `GET /metrics` (optional)

Prometheus-format metrics (when `metrics_enabled` is true).

---

## MQTT Topic Layout

### Topics Published by the Add-on

| Topic | Payload | Description |
|---|---|---|
| `fall_detector/alerts/{camera}` | JSON alert payload | Fall confirmed on camera |
| `fall_detector/status` | JSON status summary | Periodic status broadcast (every 60s) |
| `fall_detector/availability` | `online` / `offline` | Add-on availability (LWT) |
| `fall_detector/cameras/{camera}/state` | JSON camera state | Per-camera state update |

### Topics Subscribed by the Add-on

| Topic | Source | Description |
|---|---|---|
| `frigate/events` | Frigate NVR | Person detection events |
| `frigate/available` | Frigate NVR | Frigate availability |

### Topics Subscribed by the Integration

| Topic | Source | Description |
|---|---|---|
| `fall_detector/alerts/#` | Add-on | Fall alert events |
| `fall_detector/status` | Add-on | Periodic status updates |
| `fall_detector/availability` | Add-on | Add-on online/offline |
| `fall_detector/cameras/#` | Add-on | Per-camera state changes |

### Alert Payload Schema

```json
{
  "camera": "string",
  "confidence": 0.87,
  "timestamp": "2025-01-15T14:32:07.123Z",
  "event_id": "string",
  "snapshot_path": "/share/fall_detector/snapshots/camera_timestamp.jpg",
  "pose_keypoints": {
    "nose": [0.5, 0.3, 0.9],
    "left_shoulder": [0.4, 0.4, 0.85],
    "...": "..."
  },
  "confirmation_duration": 3.2,
  "scoring_details": {
    "torso_angle": 78.5,
    "vertical_compression": 0.82,
    "keypoint_y_variance": 0.03,
    "leg_hip_delta": 0.05
  }
}
```

---

## Storage and State Management

### Add-on Storage

| Path | Purpose | Retention |
|---|---|---|
| `/data/` | Add-on persistent configuration | Survives restart |
| `/share/fall_detector/snapshots/` | Alert snapshot images | User-configured, default 7 days |
| `/share/fall_detector/debug/` | Debug annotated frames | Deleted on restart (opt-in) |

### State

- **In-memory**: Per-camera confirmation state machines, cooldown timers, mute
  states, detection counts. All state is ephemeral and resets on restart.
- **MQTT retained**: `fall_detector/availability` is published with
  `retain=true` so the integration knows the add-on state immediately on
  connect.
- **No database**: The add-on does not use a database. State is kept in memory
  and communicated via MQTT/API.

### Integration Storage

- The integration stores its configuration in HA's `.storage/` directory via
  the standard config entry mechanism.
- No custom file storage.

---

## Threading and Async Model

### Add-on (FastAPI)

The add-on uses Python's `asyncio` for I/O and a thread pool for CPU-bound
inference:

```
Main Event Loop (asyncio)
├── MQTT Client (aiomqtt)
│   └── on_message → person_gate → enqueue frame task
├── FastAPI Server (uvicorn)
│   └── HTTP endpoints (all async)
├── Frame Processing Queue (asyncio.Queue)
│   └── Consumer task → fetch frame → run_in_executor(pose_estimate) → score → confirm
├── Alert Manager (async)
│   └── Publish MQTT, save snapshot, update state
└── Periodic Tasks
    ├── Status broadcast (every 60s)
    ├── Cooldown expiry check (every 1s)
    └── Debug frame cleanup (every 1h)

ThreadPoolExecutor (CPU inference)
├── MoveNet inference (TFLite)
└── Image preprocessing (OpenCV)
```

**Key design choices:**

- MQTT message handling is async. The person gate runs synchronously but is
  lightweight (microseconds).
- Frame fetching (HTTP) is async using `httpx`.
- Pose estimation (TFLite) is CPU-bound and runs in a thread pool via
  `asyncio.run_in_executor()` to avoid blocking the event loop.
- The frame processing queue has a bounded size per camera (default: 2). If
  the queue is full, new frames are dropped — this prevents memory buildup
  when inference is slower than the frame arrival rate.
- Alert publishing is async (aiomqtt).

### Integration (HA Custom Component)

The integration follows HA's standard async patterns:

- **DataUpdateCoordinator** — polls the add-on `/api/status` endpoint at the
  configured interval using `async_add_executor_job` for the HTTP request.
- **MQTT subscription** — uses HA's built-in MQTT integration
  (`homeassistant.components.mqtt`) for real-time alert consumption.
- **Entity updates** — entities subscribe to the coordinator and update their
  state when new data arrives.
- All I/O is async. No blocking calls.

```
HA Event Loop
├── DataUpdateCoordinator
│   └── async_update() → HTTP GET /api/status → update entities
├── MQTT Listener
│   └── on_message(fall_detector/alerts/#) → update entities, fire events
├── Service Handlers
│   └── async service calls → HTTP POST to add-on API
└── Entity State Updates
    └── Triggered by coordinator refresh or MQTT message
```
