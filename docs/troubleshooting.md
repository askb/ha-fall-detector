<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Troubleshooting Guide

This guide covers common issues with HA Fall Detector and how to resolve them.
If your issue is not listed here, check the
[GitHub Issues](https://github.com/askb/ha-fall-detector/issues) page.

---

## Table of Contents

- [Add-on Won't Start](#add-on-wont-start)
- [No Cameras Found](#no-cameras-found)
- [Entities Show Unavailable](#entities-show-unavailable)
- [Too Many False Positives](#too-many-false-positives)
- [No Alerts Received](#no-alerts-received)
- [MQTT Connection Failed](#mqtt-connection-failed)
- [High CPU Usage](#high-cpu-usage)
- [Entities Show Unknown State](#entities-show-unknown-state)
- [Snapshots Not Saved](#snapshots-not-saved)
- [Integration Not Found After Install](#integration-not-found-after-install)
- [Config Flow Fails](#config-flow-fails)
- [Slow Detection Response](#slow-detection-response)
- [How to Check Add-on Logs](#how-to-check-add-on-logs)
- [How to Enable Debug Logging](#how-to-enable-debug-logging)
- [How to Report a Bug](#how-to-report-a-bug)

---

## Add-on Won't Start

### Symptoms

- Add-on shows "Starting..." indefinitely or transitions to "Stopped."
- Log tab shows errors immediately after start attempt.

### Common Causes and Fixes

#### Invalid Configuration YAML

**Log message:**
```
ERROR: Failed to parse configuration: ...
```

**Fix:** Check the add-on configuration for YAML syntax errors. Common
mistakes:
- Missing quotes around strings with special characters.
- Incorrect indentation.
- Using tabs instead of spaces.

#### Frigate URL Unreachable

**Log message:**
```
ERROR: Cannot connect to Frigate at http://ccab4aaf-frigate:5000
```

**Fix:**
1. Verify Frigate is running: go to **Settings → Add-ons → Frigate** and
   check its status.
2. Verify the URL is correct. If Frigate is an HA add-on, the default
   hostname is `ccab4aaf-frigate`. If standalone, use the IP address.
3. Test connectivity:
   ```bash
   # From HA terminal (SSH add-on or Terminal add-on)
   curl -s http://ccab4aaf-frigate:5000/api/version
   ```

#### MQTT Connection Refused

**Log message:**
```
ERROR: MQTT connection refused: [Errno 111] Connection refused
```

**Fix:**
1. Verify the MQTT broker is running.
2. Check the `mqtt_host` and `mqtt_port` values.
3. Verify the username and password are correct.
4. Test from the HA terminal:
   ```bash
   mosquitto_pub -h core-mosquitto -p 1883 -u "user" -P "pass" -t "test" -m "hello"
   ```

#### Model File Missing or Corrupt

**Log message:**
```
ERROR: Failed to load TFLite model: ...
```

**Fix:** This typically indicates a corrupted Docker image. Try:
1. **Uninstall** the add-on.
2. **Reinstall** it from the add-on store.
3. Clear the Docker cache if the issue persists:
   ```bash
   # From SSH (advanced users)
   docker system prune -f
   ```

#### Port Conflict

**Log message:**
```
ERROR: Address already in use: port 5000
```

**Fix:** Another service is using port 5000. Check what is using the port:
```bash
ss -tlnp | grep 5000
```
Change the add-on port mapping in the add-on configuration or stop the
conflicting service.

---

## No Cameras Found

### Symptoms

- Add-on starts successfully but log shows "0 cameras found."
- No entities appear in Home Assistant.

### Common Causes and Fixes

#### Frigate Has No Cameras Configured

**Fix:** Verify Frigate has cameras with `detect` enabled:
1. Open the Frigate UI.
2. Verify cameras are visible and streaming.
3. Check Frigate's configuration for `detect: enabled: true`.

#### Frigate Hasn't Published Events Yet

The add-on discovers cameras from MQTT events. If Frigate hasn't seen a
person yet, no events have been published.

**Fix:**
1. Walk in front of a camera to trigger a person detection in Frigate.
2. Check Frigate's event log — you should see person detection events.
3. Check MQTT for `frigate/events` messages.

#### Camera Filter Is Too Restrictive

If you specified a `cameras` list in the add-on configuration, only those
cameras are monitored.

**Fix:** Check your `cameras` list. Camera names must exactly match Frigate's
camera names (case-sensitive). Or set `cameras: []` to auto-discover all
cameras.

#### Person Detection Not Enabled in Frigate

Frigate must be configured to detect `person` objects.

**Fix:** In Frigate's configuration, ensure each camera has:
```yaml
objects:
  track:
    - person
```

---

## Entities Show Unavailable

### Symptoms

- Fall Detector entities in HA show `unavailable` state.
- The integration appears in Devices & Services but entities have no data.

### Common Causes and Fixes

#### Add-on Is Not Running

**Fix:** Check **Settings → Add-ons → Fall Detector** — ensure it is running.
Start it if stopped.

#### Integration Cannot Reach Add-on API

The integration polls the add-on's HTTP API. If the URL is wrong or
unreachable, entities go unavailable.

**Fix:**
1. Go to **Settings → Devices & Services → Fall Detector → Configure**.
2. Verify the add-on URL.
3. Test the URL manually:
   ```
   http://homeassistant.local:5000/api/health
   ```
4. If using HA ingress, the URL may differ. Check the add-on's Web UI link.

#### MQTT Disconnected

If the integration relies on MQTT for real-time updates and MQTT is down,
entities may show stale or unavailable data.

**Fix:**
1. Check the Mosquitto add-on is running.
2. Check HA's MQTT integration is connected (**Settings → Devices & Services
   → MQTT → Configure**).

#### Integration Needs Restart

After an add-on restart, the integration may need to re-establish its
connection.

**Fix:**
1. Go to **Settings → Devices & Services → Fall Detector**.
2. Click **⋮** → **Reload**.
3. If that doesn't work, restart Home Assistant.

---

## Too Many False Positives

### Symptoms

- Frequent fall alerts when no one has fallen.
- Alerts triggered by normal activities (bending, sitting, exercising).

### Fixes

This is the most common issue. See the dedicated
[Tuning Guide](tuning.md) for comprehensive guidance. Quick fixes:

1. **Raise confidence threshold:**
   ```yaml
   confidence_threshold: 0.80  # Up from 0.70
   ```

2. **Increase confirmation time:**
   ```yaml
   confirmation_seconds: 5.0  # Up from 3.0
   ```

3. **Add zone exclusions** for couches, beds, and floor areas.

4. **Enable debug frames** to see what is triggering false alerts:
   ```yaml
   debug_frames: true
   ```
   Review frames in `/share/fall_detector/debug/` to understand the cause.

---

## No Alerts Received

### Symptoms

- Binary sensors never turn on even when a fall should be detected.
- Test alert service works but real detections don't trigger.

### Common Causes and Fixes

#### Camera Is Muted

**Fix:** Check the mute switch:
- `switch.fall_detector_{camera}_mute` — per-camera mute.
- `switch.fall_detector_global_mute` — system-wide mute.

Turn mute off if it was accidentally enabled.

#### Cooldown Is Active

After an alert fires, the camera enters a cooldown period (default 300
seconds). During cooldown, no new alerts fire for that camera.

**Fix:**
1. Wait for the cooldown to expire, or
2. Call the `fall_detector.reset_cooldown` service:
   ```yaml
   service: fall_detector.reset_cooldown
   data:
     camera: living_room
   ```

#### Confidence Threshold Is Too High

If the threshold is set too high, real falls may not meet it.

**Fix:** Lower the threshold:
```yaml
confidence_threshold: 0.60
```

See the [Tuning Guide](tuning.md) for guidance on finding the right balance.

#### Confirmation Time Is Too Long

If `confirmation_seconds` is very high, the person may recover from the fall
(or change position) before the confirmation window expires.

**Fix:** Reduce confirmation time:
```yaml
confirmation_seconds: 2.0
```

#### No Person Detected by Frigate

If Frigate doesn't detect a person, the Fall Detector never receives an event.

**Fix:**
1. Check the Frigate UI — verify person detections are occurring.
2. Ensure `person` is in the `objects.track` list for the camera.
3. Check Frigate's `min_score` and `threshold` for person detection.

#### MQTT Events Not Flowing

**Fix:**
1. Use an MQTT client to subscribe to `frigate/events` and verify events
   are being published.
2. Check the add-on log for "Received event from Frigate" messages.
3. If no events are seen, check Frigate's MQTT configuration.

---

## MQTT Connection Failed

### Symptoms

- Add-on log shows MQTT connection errors.
- Entities show unavailable or stale data.

### Common Causes and Fixes

#### Wrong Broker Address

**Fix:** Verify `mqtt_host` and `mqtt_port`:
- Mosquitto HA add-on: `core-mosquitto` port `1883`
- External broker: use IP address and port

#### Wrong Credentials

**Fix:**
1. Verify the username and password.
2. Test with `mosquitto_pub`:
   ```bash
   mosquitto_pub -h core-mosquitto -p 1883 -u "user" -P "pass" -t "test" -m "hello"
   ```
3. Check the Mosquitto add-on log for authentication errors.

#### Broker Not Running

**Fix:** Check **Settings → Add-ons → Mosquitto** and ensure it is running.

#### Broker at Capacity

If the broker is overwhelmed (too many clients, high message volume), new
connections may be rejected.

**Fix:** Check the Mosquitto log for `max_connections` errors. Increase the
limit in the Mosquitto configuration.

---

## High CPU Usage

### Symptoms

- HA system becomes sluggish.
- Add-on CPU usage is very high (visible in HA system monitor or `top`).

### Common Causes and Fixes

#### Too Many Cameras

Each camera requires dedicated CPU for pose estimation.

**Fix:** Reduce the number of monitored cameras:
```yaml
cameras:
  - living_room
  - hallway
  # Remove less critical cameras
```

#### Frame Sample Rate Too High

**Fix:** Reduce the frame rate:
```yaml
frame_sample_rate: 1.0  # Down from 2.0
```

#### Using Thunder Model on Weak Hardware

**Fix:** Switch to Lightning:
```yaml
pose_model: "lightning"
```

#### Frigate Sending Too Many Events

If Frigate's detect FPS is very high, the add-on receives many events per
second.

**Fix:**
1. Reduce Frigate's detect FPS:
   ```yaml
   # frigate.yml
   cameras:
     living_room:
       detect:
         fps: 5  # Reduce from higher values
   ```
2. The Fall Detector's `frame_sample_rate` also limits processing, but
   the MQTT event handling still has overhead.

#### Debug Frames Enabled

Saving annotated frames to disk adds I/O and CPU overhead.

**Fix:** Disable debug frames when not actively tuning:
```yaml
debug_frames: false
```

---

## Entities Show Unknown State

### Symptoms

- Entities show `unknown` instead of a value.
- This is different from `unavailable` — the entity exists but has no data.

### Fixes

This typically happens immediately after setup, before any detection has
occurred:

1. **Wait for initial data** — sensors like `last_fall` and `confidence`
   have no meaningful value until the first detection occurs. This is normal.
2. **Trigger a test alert** to populate initial values:
   ```yaml
   service: fall_detector.test_alert
   data:
     camera: living_room
   ```
3. **Walk in front of a camera** to trigger person detection (populates the
   `person_detected` binary sensor).

---

## Snapshots Not Saved

### Symptoms

- Alerts fire correctly but no snapshot images are saved.
- Notification automations show broken image links.

### Fixes

#### Shared Storage Not Accessible

**Fix:** Verify the `/share/` directory is accessible to the add-on. Check
the add-on configuration for the correct `share` mapping.

#### Disk Full

**Fix:** Check available disk space:
```bash
df -h /share/
```
Clean up old snapshots and other files if needed.

#### Frigate Snapshot API Error

If the add-on can't fetch the snapshot from Frigate, it can't save it.

**Fix:** Check the add-on logs for HTTP errors when fetching snapshots. Verify
Frigate's snapshot API is working:
```bash
curl -s http://ccab4aaf-frigate:5000/api/living_room/latest.jpg -o test.jpg
```

---

## Integration Not Found After Install

### Symptoms

- After installing via HACS, "Fall Detector" doesn't appear in the
  integration list.

### Fixes

1. **Restart Home Assistant** — the integration is not loaded until HA
   restarts.
2. **Verify HACS download** — go to HACS → Integrations → Fall Detector and
   confirm it shows as "Downloaded."
3. **Check the file system** — the integration should be at:
   ```
   /config/custom_components/fall_detector/
   ```
   Verify the directory exists and contains `__init__.py`, `manifest.json`,
   etc.
4. **Check HA logs** for import errors:
   ```
   Settings → System → Logs → Search for "fall_detector"
   ```

---

## Config Flow Fails

### Symptoms

- The integration setup wizard fails at some step with an error.

### Common Causes and Fixes

#### "Cannot connect to add-on"

**Fix:** Verify the add-on URL is correct and the add-on is running. Try
accessing the health endpoint directly in a browser.

#### "No cameras found"

**Fix:** The integration queries the add-on for cameras. If the add-on hasn't
discovered any cameras yet, the config flow fails. Ensure:
1. The add-on has started and connected to Frigate.
2. Frigate has detected at least one person (or cameras are configured
   explicitly in the add-on).
3. Wait 30 seconds after add-on start for discovery to complete.

#### "MQTT not configured"

**Fix:** The Fall Detector integration requires HA's MQTT integration to be
set up. Go to **Settings → Devices & Services** and ensure MQTT is configured.

---

## Slow Detection Response

### Symptoms

- Falls take a long time to alert (10+ seconds after the fall).

### Analysis

Detection latency = frame fetch time + pose estimation time + confirmation
time + MQTT publish time + integration poll time.

Typical breakdown:
| Stage | Typical Latency |
|---|---|
| Frame fetch (HTTP) | 50–200 ms |
| Pose estimation (Lightning) | 15–50 ms |
| Pose estimation (Thunder) | 35–130 ms |
| Confirmation window | 3,000 ms (configurable) |
| MQTT publish + subscribe | 10–50 ms |
| Integration poll | 0–30,000 ms (depends on poll interval) |

### Fixes

1. **Reduce confirmation time** (biggest impact):
   ```yaml
   confirmation_seconds: 2.0
   ```

2. **Reduce integration poll interval:**
   - Go to integration config → set poll interval to 5–10 seconds.
   - Note: MQTT-based alerts don't depend on polling and arrive in real-time.

3. **Use Lightning model** for faster inference.

4. **Increase frame sample rate** to catch the fall faster:
   ```yaml
   frame_sample_rate: 3.0
   ```

---

## How to Check Add-on Logs

### Via the HA UI

1. Go to **Settings → Add-ons → Fall Detector**.
2. Click the **Log** tab.
3. Click **Refresh** to see the latest entries.

### Via SSH

```bash
# Follow logs in real-time
docker logs addon_local_fall_detector -f --tail 100

# Search for errors
docker logs addon_local_fall_detector 2>&1 | grep -i error

# Search for a specific camera
docker logs addon_local_fall_detector 2>&1 | grep "living_room"
```

### Via HA Logs (Integration)

1. Go to **Settings → System → Logs**.
2. Search for `fall_detector`.
3. Filter by log level if needed.

---

## How to Enable Debug Logging

### Add-on Debug Logging

Set in the add-on configuration:

```yaml
log_level: "debug"
```

Then restart the add-on. Debug output includes:

- Every Frigate event received and filtering decisions.
- Every frame fetch with timing.
- Pose estimation results with keypoint details.
- Fall score computation breakdown.
- Confirmation state machine transitions.
- MQTT publish details.

> **Warning:** Debug logging is very verbose. It generates thousands of log
> lines per minute. Use only for troubleshooting, then set back to `info`.

### Integration Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.fall_detector: debug
```

Restart Home Assistant. View logs in **Settings → System → Logs**.

### Enable Debug Frames

For visual debugging:

```yaml
debug_frames: true
```

Annotated frames are saved to `/share/fall_detector/debug/{camera}/`. Access
them via:
- **Samba** share (if Samba add-on is installed)
- **SSH** to the HA host
- **File Editor** add-on (for viewing paths)

---

## How to Report a Bug

If you've exhausted the troubleshooting steps above and the issue persists:

### Before Reporting

1. ✅ Update to the latest version of the add-on and integration.
2. ✅ Reproduce the issue with `log_level: "debug"`.
3. ✅ Capture the relevant add-on logs.
4. ✅ Note your system specs (hardware, HA version, Frigate version).

### Create an Issue

Open an issue at:
[github.com/askb/ha-fall-detector/issues](https://github.com/askb/ha-fall-detector/issues)

Include:

1. **Description**: What happened and what you expected.
2. **Steps to reproduce**: Exact steps to trigger the issue.
3. **Configuration**: Your add-on config (redact passwords).
4. **Logs**: Relevant add-on and integration log excerpts.
5. **Environment**:
   - Home Assistant version
   - Frigate version
   - Hardware (RPi 4, x86, etc.)
   - Number of cameras
   - Add-on version
   - Integration version

### Sensitive Information

When sharing logs or configuration:

- ❌ **Do not include** MQTT passwords, API keys, or other credentials.
- ❌ **Do not include** screenshot images that show identifiable people.
- ✅ **Redact** sensitive values: replace passwords with `***`.
- ✅ **Crop** screenshots to show only relevant UI elements.
