<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Threat Model

This document analyzes the security properties, privacy implications, failure
modes, and deployment recommendations for HA Fall Detector. It is intended for
users evaluating whether the system meets their security and privacy
requirements.

---

## Table of Contents

- [Design Principles](#design-principles)
- [Privacy Considerations](#privacy-considerations)
- [Data Retention](#data-retention)
- [Network Security](#network-security)
- [MQTT Security](#mqtt-security)
- [Camera Feed Access](#camera-feed-access)
- [Failure Modes](#failure-modes)
- [Fail-Safe vs Fail-Open](#fail-safe-vs-fail-open)
- [Audit Logging](#audit-logging)
- [Access Control](#access-control)
- [Attack Surface](#attack-surface)
- [Recommendations for Production Deployment](#recommendations-for-production-deployment)

---

## Design Principles

HA Fall Detector is designed around these security principles:

1. **Local-only processing** — no data leaves the local network. Zero cloud
   dependencies, zero telemetry, zero external API calls.
2. **Minimal data retention** — frames are processed in memory and discarded.
   Only alert snapshots are persisted, with configurable retention.
3. **No identity information** — the system detects body poses, not faces or
   identities. It cannot tell *who* fell, only *that* a fall occurred.
4. **Least privilege** — the add-on only accesses what it needs: Frigate's
   API, the MQTT broker, and local shared storage.
5. **Transparent operation** — all detection logic is open source and auditable.

---

## Privacy Considerations

### What Data Is Processed

| Data Type | Processed? | Stored? | Duration |
|---|---|---|---|
| Raw camera video stream | **No** — Frigate handles this | No | N/A |
| Frigate MQTT events (JSON) | Yes — parsed for person detection | No (in-memory only) | Discarded after processing |
| Frigate snapshots (JPEG) | Yes — fetched via HTTP, analyzed | No (in-memory only) | Discarded after pose estimation |
| Pose keypoints (17 points) | Yes — computed from snapshots | Briefly (in alert payloads) | Included in MQTT alert; not persisted to disk |
| Alert snapshots | Yes — saved on confirmed fall | **Yes** — to shared storage | Configurable retention (default 7 days) |
| Debug frames (annotated) | Only if enabled | **Yes** — to shared storage | Deleted on add-on restart |
| Detection scores | Yes — computed per frame | No (in-memory only) | Discarded after confirmation logic |
| Configuration data | Yes | Yes — in add-on data | Until reconfigured |

### What Is NOT Collected

- **No facial recognition** — MoveNet estimates body skeleton only.
- **No person identification** — the system has no concept of identity.
- **No audio** — only visual frame data is analyzed.
- **No behavior profiling** — there is no pattern-of-life analysis.
- **No cloud communication** — the add-on makes zero outbound internet
  requests.
- **No telemetry** — no usage data, crash reports, or analytics are sent
  anywhere.
- **No third-party dependencies at runtime** — no external APIs, CDNs,
  or services are contacted.

### Snapshot Privacy

Alert snapshots contain the full Frigate camera frame (not just the person
crop). This means:

- The snapshot may show other people in the frame.
- The snapshot shows the room and its contents.
- If sent as a notification image, it travels to the notification service
  (e.g., Apple/Google push notification servers).

**Mitigation:**
- Reduce snapshot retention to the minimum needed.
- Be aware that push notifications with images route through third-party
  servers (Apple APNs, Google FCM) — this is inherent to mobile push, not
  specific to this project.
- Consider automations that omit the snapshot image if privacy is critical.

---

## Data Retention

### Default Retention

| Data | Location | Default Retention | Configurable? |
|---|---|---|---|
| Alert snapshots | `/share/fall_detector/snapshots/` | 7 days | Yes (via cleanup automation) |
| Debug frames | `/share/fall_detector/debug/` | Deleted on restart | Yes (`debug_frames: false` disables entirely) |
| Add-on logs | Docker log driver | Follows HAOS defaults | Yes (via Docker log config) |
| MQTT messages | Broker memory | Not retained (QoS 0/1) | Retained messages for availability only |
| In-memory state | Add-on process memory | Lost on restart | N/A |

### Minimizing Data Retention

For the most privacy-conscious deployment:

1. **Disable debug frames** (default):
   ```yaml
   debug_frames: false
   ```
2. **Reduce snapshot retention**: Create an automation to delete old snapshots.
3. **Disable snapshot saving** (future feature, or modify the add-on to skip
   snapshot persistence).
4. **Remove notification images**: Build automations that alert without
   including the snapshot.

---

## Network Security

### Add-on API Access

The Fall Detector add-on runs a FastAPI HTTP server on port 5000. Access
characteristics:

| Property | Value |
|---|---|
| **Bind address** | `0.0.0.0` inside the container |
| **Exposed via** | HA ingress proxy (default) or direct port mapping |
| **Authentication** | None (by design — internal use only) |
| **TLS** | None (local network only) |
| **CORS** | Not configured (not a browser API) |

### Ingress (Recommended)

When accessed through HA ingress (the default for add-ons), the API is:

- Proxied through HA Core.
- Protected by HA authentication (users must be logged into HA).
- Not directly exposed to the network.
- Accessible only through the HA frontend or authenticated API calls.

### Direct Port Mapping (Not Recommended)

If the add-on port is directly mapped to the host network:

- The API is accessible to any device on the local network.
- No authentication is enforced.
- Any device can call `POST /api/test_alert`, `POST /api/mute/{camera}`, etc.

**Recommendation:** Use HA ingress and do not expose port 5000 directly. If
direct access is needed (e.g., for external monitoring), place it behind a
reverse proxy with authentication.

### Network Isolation

The add-on communicates only with:

| Destination | Protocol | Purpose |
|---|---|---|
| Frigate NVR | HTTP | Fetch snapshots |
| MQTT broker | TCP (MQTT) | Subscribe to events, publish alerts |
| HA Core | HTTP (ingress proxy) | Serve status API |
| Shared storage | Filesystem | Save snapshots, debug frames |

The add-on does **not** communicate with:

- The internet (no outbound connections).
- Cameras directly (all camera access is through Frigate).
- Other add-ons (except Frigate and Mosquitto via their APIs).

---

## MQTT Security

### Default Configuration

By default on a local HA installation:

| Property | Value |
|---|---|
| TLS | Not enabled (local network assumed secure) |
| Authentication | Username/password (configured in Mosquitto) |
| Authorization | All authenticated users can pub/sub to all topics |
| Retained messages | Used for availability topics only |

### MQTT Threat Scenarios

| Threat | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **Eavesdropping on MQTT** | Attacker sees alert topics, knows when falls occur | Low (requires LAN access) | Enable TLS on MQTT broker |
| **Spoofed alert injection** | Attacker publishes fake fall alert to MQTT | Low (requires MQTT credentials) | Use MQTT ACLs to restrict publishing; separate user for add-on |
| **Denial of service** | Attacker floods MQTT with messages | Low (requires LAN access) | Rate limiting on MQTT broker; network segmentation |
| **Mute injection** | Attacker publishes mute command via API | Low (requires API access) | Use HA ingress; don't expose port directly |

### Hardening MQTT

For higher security:

1. **Enable TLS** on the Mosquitto broker:
   ```yaml
   # mosquitto.conf
   listener 8883
   certfile /etc/mosquitto/certs/server.crt
   keyfile /etc/mosquitto/certs/server.key
   ```

2. **Use MQTT ACLs** to restrict topic access:
   ```
   user fall_detector
   topic readwrite fall_detector/#
   topic read frigate/events
   topic read frigate/available
   ```

3. **Separate MQTT users** for each service (Frigate, Fall Detector, HA).

---

## Camera Feed Access

### Access Model

The Fall Detector add-on does **not** access cameras directly:

```
Camera ──RTSP──▶ Frigate ──HTTP (snapshot)──▶ Fall Detector
                         ──MQTT (event)──────▶ Fall Detector
```

- The add-on has no RTSP client.
- The add-on has no camera credentials.
- The add-on only receives:
  - JSON event metadata from Frigate (via MQTT).
  - JPEG snapshot images from Frigate (via HTTP API).
- Frigate controls what is exposed and at what resolution.

### Implications

- **Adding a camera** to Fall Detector requires adding it to Frigate first.
- **Camera credentials** are stored only in Frigate's configuration.
- **Stream encryption** (RTSPS) is between the camera and Frigate; the Fall
  Detector is not involved.
- **Snapshot resolution** is controlled by Frigate's detect resolution setting.

---

## Failure Modes

Understanding how the system fails is critical for a safety-relevant
application.

### Failure Scenarios

| Failure | Detection Impact | Alert Impact | Recovery |
|---|---|---|---|
| **Add-on crashes** | All detection stops | No alerts can fire | Supervisor watchdog restarts (if enabled); entities show `unavailable` |
| **Frigate crashes** | No person events received | Detection stops | Frigate watchdog restarts; add-on reconnects automatically |
| **MQTT broker down** | No events received; no alerts published | Detection and alerting both stop | Broker restart; auto-reconnect with backoff |
| **Camera goes offline** | Frigate stops sending events for that camera | No detection for that camera | Camera comes back; Frigate resumes; add-on resumes |
| **Network partition (add-on ↔ Frigate)** | Can't fetch snapshots | Detection stops | Network restored; auto-reconnect |
| **Network partition (add-on ↔ MQTT)** | Can't receive events or publish alerts | Both stop | MQTT reconnect with exponential backoff |
| **High CPU load** | Frame processing queue fills up; frames dropped | Delayed or missed detections | Reduce `frame_sample_rate` or number of cameras |
| **Disk full** | Snapshot/debug frame save fails | Alert fires but without snapshot | Clean up storage; snapshot save failure is non-fatal |
| **Out of memory** | Add-on process killed by OOM killer | All detection stops | Supervisor restarts; reduce cameras or frame rate |
| **TFLite model corruption** | Inference produces garbage results | Incorrect scores (false positives or negatives) | Re-download model on next add-on rebuild |

### Detection of Failures

The system provides several indicators of failure:

| Indicator | Entity | Meaning |
|---|---|---|
| Add-on offline | `fall_detector/availability` MQTT (LWT) | Add-on process has stopped |
| Camera offline | `binary_sensor.fall_detector_{camera}_online` | No events received for camera recently |
| System degraded | `sensor.fall_detector_system_status` | One or more subsystems unhealthy |
| System error event | `fall_detector_system_error` HA event | Specific error occurred |
| Health endpoint | `/api/health` HTTP | Direct add-on health check |

---

## Fail-Safe vs Fail-Open

This is the most important design decision for a safety system.

### Current Behavior: Fail-Open

HA Fall Detector currently operates in a **fail-open** mode:

- When the system fails (crash, disconnect, etc.), **no alerts are generated**.
- The system does **not** assume a fall has occurred during a failure.
- Entities show `unavailable`, which can be used to trigger a "system down"
  notification.

### Why Fail-Open?

- **Fail-safe** (alerting on failure) would mean every system restart, MQTT
  hiccup, or network blip generates a false fall alert. This leads to alert
  fatigue, which is arguably more dangerous than a missed alert — users learn
  to ignore alerts.
- A dedicated "system down" notification is more useful: it tells the user
  monitoring is interrupted so they can check in manually.

### Recommended: Monitor System Health

Build an automation that alerts you when the system itself goes down:

```yaml
automation:
  - alias: "Fall Detector System Down Alert"
    trigger:
      - platform: state
        entity_id: sensor.fall_detector_system_status
        to: "unavailable"
        for:
          minutes: 2
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "⚠️ Fall Detector Offline"
          message: >
            The Fall Detector system has been offline for 2 minutes.
            Fall monitoring is NOT active. Please check the system.
```

This way, you get two layers of notification:
1. Fall alert → someone may have fallen.
2. System down alert → monitoring is interrupted, check in manually.

---

## Audit Logging

### What Is Logged

The add-on logs the following events (at `info` level):

| Event | Logged Data | Sensitivity |
|---|---|---|
| Startup | Version, configured cameras, model type | Low |
| MQTT connect/disconnect | Broker address, connection status | Low |
| Frigate connect/disconnect | Frigate URL, connection status | Low |
| Fall detected | Camera name, confidence score, timestamp | Medium |
| Alert published | Camera name, MQTT topic | Medium |
| Alert muted/unmuted | Camera name, who triggered (API/switch) | Low |
| Cooldown started/reset | Camera name, duration | Low |
| Test alert fired | Camera name, source | Low |
| Error conditions | Error details, stack traces | Medium |

### What Is NOT Logged

- Snapshot image data (never logged, only saved to file).
- Pose keypoint coordinates (only at `debug` level).
- MQTT message payloads (only at `debug` level).
- Camera credentials (never — the add-on doesn't have them).

### Log Destinations

- **Add-on logs**: Written to Docker stdout/stderr, captured by the HA
  Supervisor, viewable in the add-on Log tab.
- **Integration logs**: Written to HA's standard logging system, viewable
  in Settings → System → Logs.

### Log Rotation

HA Supervisor manages add-on log rotation. Default behavior keeps the last
~100 KB of logs. For longer retention, configure Docker's logging driver.

---

## Access Control

### Who Can Access What

| Actor | Add-on API | MQTT Topics | Snapshots | Configuration |
|---|---|---|---|---|
| **HA Admin** | ✅ Full access (via ingress) | ✅ Via MQTT Explorer or HA | ✅ Via Samba/SSH | ✅ Add-on config + integration options |
| **HA User** | ✅ Via HA services/entities | ⚠️ Only if given MQTT access | ⚠️ Only if file access is granted | ⚠️ Via integration options only |
| **Local network device** | ⚠️ Only if port 5000 is exposed | ⚠️ Only if MQTT credentials known | ❌ No direct file access | ❌ No access |
| **External/internet** | ❌ Not exposed (by default) | ❌ Not exposed | ❌ Not exposed | ❌ Not exposed |
| **The add-on itself** | N/A (is the API server) | ✅ Pub/sub with credentials | ✅ Filesystem write | ✅ Reads own config |
| **The integration** | ✅ HTTP client | ✅ MQTT subscriber (via HA) | ❌ No direct file access | ✅ HA config entry |

### Principle of Least Privilege

The add-on operates with minimal permissions:

- **Filesystem**: Read/write to `/data/` (own config) and `/share/` (snapshots).
  No access to HA core data, other add-on data, or system files.
- **Network**: Outbound to Frigate HTTP and MQTT broker only. No internet
  access required or used.
- **HA API**: The add-on does not use the HA Supervisor API or HA Core API.
  Communication is exclusively through MQTT and its own HTTP API.

---

## Attack Surface

### External Attack Surface

**None by default.** The system has no internet-facing components. All
communication is local.

If the HA instance is exposed to the internet (via Nabu Casa, a reverse
proxy, or port forwarding), the Fall Detector itself is not directly exposed.
However, HA services that wrap Fall Detector functionality would be accessible
through HA's authentication layer.

### Local Network Attack Surface

| Component | Port/Protocol | Authentication | Risk |
|---|---|---|---|
| Add-on HTTP API | 5000/TCP (if exposed) | None | Medium — can trigger test alerts, mute cameras |
| MQTT topics | 1883/TCP | Username/password | Low–Medium — can inject fake alerts or mute commands |
| Shared filesystem | N/A (local) | OS file permissions | Low — requires SSH/Samba access |

### Supply Chain

| Dependency | Source | Risk | Mitigation |
|---|---|---|---|
| TensorFlow Lite | Google (pip) | Low | Pinned version in requirements.txt |
| MoveNet model | TensorFlow Hub | Low | Bundled in Docker image at build time |
| FastAPI | PyPI | Low | Pinned version |
| OpenCV | PyPI | Low | Pinned version |
| Python base image | Docker Hub | Low–Medium | Use official slim images; pin digest |
| HA integration deps | HA Core | Low | Uses HA's dependency management |

---

## Recommendations for Production Deployment

### Minimum Security

These are the baseline steps for any deployment:

1. ✅ **Use HA ingress** — do not expose the add-on port directly.
2. ✅ **Use MQTT authentication** — configure username/password on the broker.
3. ✅ **Enable Supervisor watchdog** — auto-restart on crash.
4. ✅ **Monitor system health** — create a "system down" automation.
5. ✅ **Minimize snapshot retention** — set retention to 1–3 days.
6. ✅ **Disable debug frames in production** — only enable for tuning.

### Enhanced Security

For higher-security deployments (e.g., care facilities):

7. ✅ **Enable MQTT TLS** — encrypt broker communication.
8. ✅ **Use MQTT ACLs** — restrict per-user topic access.
9. ✅ **Network segmentation** — put cameras and Frigate on a separate VLAN.
10. ✅ **Disable port mapping** — ensure the add-on port is not mapped to
    the host.
11. ✅ **Regular updates** — keep the add-on, integration, Frigate, and HA
    up to date.
12. ✅ **Log monitoring** — forward logs to a centralized system for review.
13. ✅ **Physical security** — secure the HA host and camera hardware.

### DO NOT Rely On This System Alone

This system is **assistive**, not primary. For any real care scenario:

- ✅ **Use a certified medical alert device** (PERS) as the primary system.
- ✅ **Regular in-person check-ins** by caregivers.
- ✅ **Redundant notification channels** — don't rely on a single phone.
- ✅ **Test regularly** — use the test alert service weekly to verify the
  pipeline works end to end.
- ✅ **Have a response plan** — know what to do when an alert fires (who to
  call, how to check on the person).
