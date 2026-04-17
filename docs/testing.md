<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Testing Guide

This guide covers how to run the test suite, test components locally, validate
the system before trusting it for real monitoring, and generate synthetic test
data.

---

## Table of Contents

- [Test Overview](#test-overview)
- [Running the Test Suite](#running-the-test-suite)
- [Testing the Add-on Locally](#testing-the-add-on-locally)
- [Testing the Integration](#testing-the-integration)
- [Using the Test Alert Service](#using-the-test-alert-service)
- [Safe Validation Checklist](#safe-validation-checklist)
- [Test Scenarios to Verify](#test-scenarios-to-verify)
- [Generating Synthetic Test Data](#generating-synthetic-test-data)

---

## Test Overview

HA Fall Detector has tests at multiple levels:

| Level | Component | Framework | Location |
|---|---|---|---|
| Unit tests | Add-on | pytest | `addon/fall_detector/tests/` |
| Unit tests | Integration | pytest + HA test helpers | `custom_components/fall_detector/tests/` |
| Integration tests | Add-on | pytest + Docker | `addon/fall_detector/tests/integration/` |
| End-to-end tests | Full system | Manual + test alert service | N/A (manual) |
| Linting | Both | ruff, yamllint, mypy | Pre-commit hooks |

---

## Running the Test Suite

### Prerequisites

- Python 3.12+
- A Python virtual environment (recommended)
- Development dependencies installed

### Setup

```bash
# Clone the repository
git clone https://github.com/askb/ha-fall-detector.git
cd ha-fall-detector

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -e ".[dev]"

# Or install from requirements files
pip install -r requirements-dev.txt
```

### Run All Tests

```bash
# Run the full test suite
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=addon/fall_detector --cov=custom_components/fall_detector --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run Add-on Tests Only

```bash
# All add-on tests
pytest addon/fall_detector/tests/

# Specific test module
pytest addon/fall_detector/tests/test_pipeline.py

# Specific test function
pytest addon/fall_detector/tests/test_scoring.py::test_standing_person_low_score

# Run with debug output
pytest addon/fall_detector/tests/ -v -s
```

### Run Integration Tests Only

```bash
# All integration tests
pytest custom_components/fall_detector/tests/

# Specific test
pytest custom_components/fall_detector/tests/test_config_flow.py
```

### Run Linters

```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Run specific linters
ruff check .
ruff format --check .
yamllint .
mypy addon/fall_detector/
```

---

## Testing the Add-on Locally

You can build and run the add-on Docker container locally for testing without
a full Home Assistant installation.

### Build the Docker Image

```bash
cd addon/fall_detector

# Build the image
docker build -t fall-detector-test .

# Verify the build
docker images fall-detector-test
```

### Run with Mock Services

For local testing, you need mock Frigate and MQTT services. A Docker Compose
file is provided:

```bash
cd addon/fall_detector

# Start the test environment (add-on + mock Frigate + MQTT broker)
docker compose -f docker-compose.test.yaml up -d

# View logs
docker compose -f docker-compose.test.yaml logs -f fall-detector

# Stop the environment
docker compose -f docker-compose.test.yaml down
```

The test environment includes:

| Service | Port | Description |
|---|---|---|
| `fall-detector` | 5000 | The add-on under test |
| `mosquitto` | 1883 | MQTT broker |
| `mock-frigate` | 5001 | Mock Frigate API serving test images |

### Run the Container Directly

If you want to run just the add-on container with external dependencies:

```bash
docker run -d \
  --name fall-detector-test \
  -p 5000:5000 \
  -e FRIGATE_URL=http://host.docker.internal:5000 \
  -e MQTT_HOST=host.docker.internal \
  -e MQTT_PORT=1883 \
  -e LOG_LEVEL=debug \
  fall-detector-test
```

### Test the API

Once the container is running:

```bash
# Health check
curl -s http://localhost:5000/api/health | python3 -m json.tool

# Status
curl -s http://localhost:5000/api/status | python3 -m json.tool

# Trigger a test alert
curl -s -X POST http://localhost:5000/api/test_alert \
  -H "Content-Type: application/json" \
  -d '{"camera": "test_camera", "confidence": 0.90}' | python3 -m json.tool

# Mute a camera
curl -s -X POST http://localhost:5000/api/mute/test_camera | python3 -m json.tool

# Unmute a camera
curl -s -X POST http://localhost:5000/api/unmute/test_camera | python3 -m json.tool
```

### Test with Real Frigate

If you have Frigate running somewhere on your network:

```bash
docker run -d \
  --name fall-detector-test \
  -p 5000:5000 \
  -e FRIGATE_URL=http://192.168.1.100:5000 \
  -e MQTT_HOST=192.168.1.100 \
  -e MQTT_PORT=1883 \
  -e MQTT_USER=your_user \
  -e MQTT_PASSWORD=your_pass \
  -e LOG_LEVEL=debug \
  -e CONFIDENCE_THRESHOLD=0.70 \
  fall-detector-test
```

---

## Testing the Integration

The integration uses Home Assistant's test framework (`pytest-homeassistant-custom-component`).

### Setup

```bash
# Install HA test dependencies
pip install pytest-homeassistant-custom-component

# Run integration tests
pytest custom_components/fall_detector/tests/ -v
```

### Test Structure

```
custom_components/fall_detector/tests/
├── conftest.py              # Shared fixtures (mock HA, mock MQTT, mock API)
├── test_config_flow.py      # Config flow tests (setup wizard)
├── test_coordinator.py      # Data update coordinator tests
├── test_binary_sensor.py    # Binary sensor entity tests
├── test_sensor.py           # Sensor entity tests
├── test_switch.py           # Switch entity tests
├── test_services.py         # Service call tests
├── test_events.py           # Event firing tests
└── test_diagnostics.py      # Diagnostics data tests
```

### Key Test Fixtures

```python
# conftest.py provides these fixtures:

@pytest.fixture
def mock_addon_api():
    """Mock the Fall Detector add-on HTTP API responses."""
    # Returns mock status, health, camera data
    ...

@pytest.fixture
def mock_mqtt():
    """Mock MQTT message delivery for alert testing."""
    # Simulates MQTT alert messages
    ...

@pytest.fixture
def mock_config_entry():
    """Create a mock config entry for the integration."""
    ...
```

### Running Specific Integration Tests

```bash
# Test config flow
pytest custom_components/fall_detector/tests/test_config_flow.py -v

# Test that a fall alert creates the right entity states
pytest custom_components/fall_detector/tests/test_binary_sensor.py::test_fall_detected_turns_on -v

# Test service calls
pytest custom_components/fall_detector/tests/test_services.py -v
```

---

## Using the Test Alert Service

The `fall_detector.test_alert` service is the primary tool for end-to-end
testing in a live system. It simulates a complete fall detection event without
requiring a real fall.

### From the HA UI

1. Go to **Developer Tools → Services**.
2. Select `fall_detector.test_alert`.
3. Enter parameters:
   ```yaml
   camera: living_room
   confidence: 0.90
   ```
4. Click **Call Service**.
5. Observe:
   - `binary_sensor.fall_detector_living_room_fall_detected` turns `on`.
   - `sensor.fall_detector_living_room_confidence` shows `90`.
   - Any automations triggered by the event fire.
   - The alert auto-clears after a few seconds.

### From an Automation

You can create a test automation that triggers at a specific time or on
button press:

```yaml
automation:
  - alias: "Test Fall Alert (Button Trigger)"
    trigger:
      - platform: state
        entity_id: input_button.test_fall_alert
        to: ~
    action:
      - service: fall_detector.test_alert
        data:
          camera: living_room
          confidence: 0.85
```

### From the Command Line

```bash
# Via HA REST API
curl -X POST \
  -H "Authorization: Bearer YOUR_LONG_LIVED_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "fall_detector.test_alert", "camera": "living_room", "confidence": 0.90}' \
  http://homeassistant.local:8123/api/services/fall_detector/test_alert
```

### What the Test Alert Does

1. The integration sends an HTTP POST to the add-on's `/api/test_alert`
   endpoint.
2. The add-on creates a synthetic alert event with the specified camera and
   confidence.
3. The add-on publishes this alert to MQTT on
   `fall_detector/alerts/{camera}`.
4. The integration receives the MQTT alert and updates entities.
5. The alert auto-clears after 10 seconds (test alerts have a short TTL).

### What the Test Alert Does NOT Do

- It does **not** run the actual detection pipeline (no pose estimation).
- It does **not** save a real snapshot (a placeholder image is used).
- It does **not** enter the confirmation state machine.
- It **does** trigger real cooldown (the camera enters cooldown after the
  test alert). Use `fall_detector.reset_cooldown` to clear it.

---

## Safe Validation Checklist

Before trusting the system for real monitoring, work through this checklist:

### System Health

- [ ] Add-on is running and shows `healthy` status.
- [ ] All monitored cameras show as `online`.
- [ ] `sensor.fall_detector_system_status` shows `healthy`.
- [ ] MQTT connection is established (check add-on logs).
- [ ] Frigate connection is established (check add-on logs).

### Entity Verification

- [ ] Each camera has all expected entities (binary sensors, sensors, switches).
- [ ] `binary_sensor.fall_detector_{camera}_online` is `on` for all cameras.
- [ ] `binary_sensor.fall_detector_{camera}_person_detected` updates when
      someone walks in front of the camera.
- [ ] `sensor.fall_detector_{camera}_pipeline_latency` shows reasonable values
      (< 200 ms for Lightning, < 400 ms for Thunder).

### Test Alert Pipeline

- [ ] Call `fall_detector.test_alert` for each camera.
- [ ] Verify the binary sensor turns on.
- [ ] Verify the confidence sensor updates.
- [ ] Verify the detection count increments.
- [ ] Verify your notification automation fires.
- [ ] Verify the alert auto-clears after ~10 seconds.

### Mute/Unmute

- [ ] Mute a camera → trigger test alert → verify NO notification.
- [ ] Unmute the camera → trigger test alert → verify notification fires.
- [ ] Enable global mute → trigger test alert → verify NO notification.
- [ ] Disable global mute → trigger test alert → verify notification fires.

### Cooldown

- [ ] Trigger a test alert → immediately trigger another → verify the second
      is suppressed (cooldown active).
- [ ] Call `fall_detector.reset_cooldown` → trigger test alert → verify it
      fires.

### System Down Monitoring

- [ ] Stop the add-on → verify `system_status` goes to `unavailable`.
- [ ] Verify your "system down" automation fires (if configured).
- [ ] Restart the add-on → verify entities recover to normal.

### False Positive Check

- [ ] Enable debug frames.
- [ ] Walk normally in front of each camera — no false alerts.
- [ ] Sit on a chair/couch — no false alerts (with zone exclusions if
      applicable).
- [ ] Bend to pick something up — no false alerts (within confirmation
      window).
- [ ] Review debug frames for any anomalies.
- [ ] Disable debug frames when done.

---

## Test Scenarios to Verify

### Detection Scenarios

| Scenario | Expected Outcome | How to Test |
|---|---|---|
| Person standing | No alert | Walk normally in camera view |
| Person sitting in chair | No alert | Sit in a chair within camera view |
| Person lying on couch | No alert (with exclusion zone) | Lie on couch with zone exclusion configured |
| Person bending briefly | No alert (within confirmation window) | Bend down for < 3 seconds |
| Controlled fall test | Alert fires after confirmation | **Carefully** lower yourself to the ground (use padding) |
| Person leaves frame | State resets | Walk out of camera view; confirm state returns to IDLE |
| Two people in frame | Detection continues | Have two people in view; one stands, one lies down |
| No person in frame | No processing | Verify no CPU usage when room is empty |

### System Scenarios

| Scenario | Expected Outcome | How to Test |
|---|---|---|
| Add-on restart | Entities go unavailable, then recover | Restart the add-on |
| MQTT broker restart | Reconnects automatically | Restart Mosquitto |
| Frigate restart | Detection pauses, then resumes | Restart Frigate |
| Camera goes offline | Camera entity shows offline | Disconnect a camera |
| Multiple simultaneous falls | Each camera alerts independently | Test alerts on two cameras at once |
| High CPU load | Frames dropped but system continues | Run a CPU-intensive task alongside |

### Automation Scenarios

| Scenario | Expected Outcome | How to Test |
|---|---|---|
| Push notification | Received on phone with correct data | Trigger test alert |
| Light flash | Light flashes red on fall | Trigger test alert |
| TTS announcement | Speaker announces fall | Trigger test alert |
| Muted camera notification | No notification sent | Mute camera, trigger test alert |
| Alert cleared notification | Received clear notification | Trigger test alert, wait for auto-clear |

---

## Generating Synthetic Test Data

### MQTT Event Simulation

You can simulate Frigate events by publishing directly to MQTT:

```bash
# Simulate a person detection event from Frigate
mosquitto_pub -h core-mosquitto -p 1883 -u "user" -P "pass" \
  -t "frigate/events" \
  -m '{
    "type": "new",
    "before": {},
    "after": {
      "id": "test-event-001",
      "camera": "living_room",
      "label": "person",
      "top_score": 0.95,
      "score": 0.92,
      "box": [0.2, 0.3, 0.5, 0.9],
      "area": 0.18,
      "ratio": 0.5,
      "region": [0.0, 0.0, 1.0, 1.0],
      "stationary": false,
      "motionless_count": 0,
      "position_changes": 1,
      "current_zones": [],
      "entered_zones": [],
      "has_snapshot": true,
      "has_clip": false
    }
  }'
```

### Test Image Generation

The add-on's test suite includes utilities for generating synthetic pose data:

```python
# addon/fall_detector/tests/utils/generate_test_data.py

from fall_detector.tests.utils import generate_standing_pose, generate_fallen_pose

# Generate keypoints for a standing person
standing = generate_standing_pose()
# Returns: dict with 17 keypoints, all at expected standing positions

# Generate keypoints for a person who has fallen
fallen = generate_fallen_pose()
# Returns: dict with 17 keypoints, all at horizontal positions

# Generate keypoints with noise
noisy_fallen = generate_fallen_pose(noise_level=0.05)
# Adds random noise to keypoint positions for realism
```

### Batch Event Simulation Script

For stress testing or generating a sequence of events:

```python
#!/usr/bin/env python3
"""Generate a sequence of synthetic Frigate events for testing."""

import json
import time
import paho.mqtt.client as mqtt

BROKER = "core-mosquitto"
PORT = 1883
USER = "test_user"
PASSWORD = "test_pass"

client = mqtt.Client()
client.username_pw_set(USER, PASSWORD)
client.connect(BROKER, PORT)

def publish_event(camera: str, event_type: str, event_id: str):
    """Publish a synthetic Frigate event."""
    payload = {
        "type": event_type,
        "before": {},
        "after": {
            "id": event_id,
            "camera": camera,
            "label": "person",
            "top_score": 0.95,
            "score": 0.92,
            "box": [0.2, 0.3, 0.5, 0.9],
            "area": 0.18,
            "ratio": 0.5,
            "region": [0.0, 0.0, 1.0, 1.0],
            "stationary": False,
            "motionless_count": 0,
            "position_changes": 1,
            "current_zones": [],
            "entered_zones": [],
            "has_snapshot": True,
            "has_clip": False,
        },
    }
    client.publish("frigate/events", json.dumps(payload))

# Simulate a person appearing, being tracked, and then leaving
event_id = "sim-001"
publish_event("living_room", "new", event_id)
time.sleep(0.5)

for i in range(10):
    publish_event("living_room", "update", event_id)
    time.sleep(0.5)

publish_event("living_room", "end", event_id)

client.disconnect()
print("Simulation complete.")
```

### Mock Frigate Server

For local add-on testing, a mock Frigate server serves test images:

```python
#!/usr/bin/env python3
"""Minimal mock Frigate HTTP API for testing."""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# A 1x1 pixel JPEG (smallest valid JPEG)
TINY_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
    0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
    0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x40,
    0x1B, 0xFF, 0xD9
])


class MockFrigateHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/version":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps("0.13.0").encode())
        elif "/latest.jpg" in self.path:
            # Return a test JPEG for snapshot requests
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            # In real testing, use a proper test image with a person
            self.wfile.write(TINY_JPEG)
        elif self.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            config = {
                "cameras": {
                    "living_room": {"enabled": True},
                    "hallway": {"enabled": True},
                }
            }
            self.wfile.write(json.dumps(config).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 5001), MockFrigateHandler)
    print("Mock Frigate server running on port 5001")
    server.serve_forever()
```

### Using Real Test Images

For more realistic testing, place test images in
`addon/fall_detector/tests/fixtures/`:

```
tests/fixtures/
├── standing_person_01.jpg    # Person standing upright
├── standing_person_02.jpg    # Person walking
├── sitting_person_01.jpg     # Person sitting in chair
├── fallen_person_01.jpg      # Person lying on floor (simulated)
├── fallen_person_02.jpg      # Person in recovery position
├── empty_room_01.jpg         # Empty room (no person)
└── two_people_01.jpg         # Two people, one standing, one sitting
```

These images can be used with the mock Frigate server or directly in unit
tests for the scoring algorithm.

> **Important:** Do not include images of real falls or real people in the
> test fixtures. Use posed/staged images with consenting participants, or
> use synthetic/mannequin images.
