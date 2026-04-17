<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Tuning Guide

This guide helps you optimize fall detection accuracy and minimize false
positives. Every home is different — camera angles, lighting, room layouts,
and the people being monitored all affect detection quality. Expect to spend
some time tuning after initial installation.

---

## Table of Contents

- [Understanding Confidence Thresholds](#understanding-confidence-thresholds)
- [Reducing False Positives](#reducing-false-positives)
- [Reducing Missed Detections](#reducing-missed-detections)
- [Camera Placement Tips](#camera-placement-tips)
- [Per-Camera Threshold Adjustments](#per-camera-threshold-adjustments)
- [Zone Exclusion Guide](#zone-exclusion-guide)
- [Time-of-Day Considerations](#time-of-day-considerations)
- [Frame Sample Rate Tuning](#frame-sample-rate-tuning)
- [Pose Backend Selection](#pose-backend-selection)
- [Common False Positive Scenarios](#common-false-positive-scenarios)
- [Logging for Debugging](#logging-for-debugging)
- [Iterative Tuning Workflow](#iterative-tuning-workflow)

---

## Understanding Confidence Thresholds

The confidence threshold controls how certain the system must be before
triggering an alert. It is a value between 0.0 and 1.0:

| Value | Meaning | Trade-off |
|---|---|---|
| `0.50` | Very sensitive | Catches more falls but many false positives |
| `0.60` | Sensitive | Good for high-risk individuals; some false positives |
| `0.70` | **Balanced (default)** | Reasonable balance of sensitivity and specificity |
| `0.80` | Conservative | Fewer false positives but may miss some falls |
| `0.90` | Very conservative | Very few false positives; higher risk of missed falls |

**How the score is calculated:**

The fall confidence score combines multiple geometric features from the
detected body pose (see [Architecture](architecture.md#fall-scoring) for
details):

- **Torso angle** (40% weight) — how far the torso has rotated from vertical.
- **Vertical compression** (25% weight) — how compressed the body is vertically
  compared to standing height.
- **Keypoint y-variance** (20% weight) — how spread out keypoints are
  vertically (low variance = horizontal body).
- **Leg-hip delta** (15% weight) — height difference between hips and ankles.

A **standing person** typically scores 0.05–0.20.
A **sitting person** typically scores 0.20–0.45.
A **person lying on the floor** typically scores 0.70–0.95.

The threshold determines where to draw the line between "not a fall" and
"possible fall."

---

## Reducing False Positives

False positives are the most common issue. Here are strategies ordered from
most to least effective:

### 1. Raise the Confidence Threshold

The simplest adjustment. If you're getting too many false alerts:

```yaml
# Add-on configuration
confidence_threshold: 0.80  # Up from default 0.70
```

Start by increasing in increments of 0.05 and monitoring for a few days.

### 2. Increase the Confirmation Time

The confirmation window requires the fall posture to be sustained for a
minimum duration. Increasing it filters out transient poses:

```yaml
confirmation_seconds: 5.0  # Up from default 3.0
```

A person tying their shoes is typically in a low position for 2–5 seconds.
Setting confirmation to 5–8 seconds filters most of these.

**Trade-off:** Higher confirmation time means a real fall takes longer to
alert. For a 5-second window, the alert fires ~5 seconds after the fall
occurs (plus processing latency).

### 3. Use Zone Exclusions

Exclude areas where horizontal postures are expected — beds, couches,
recliners, floor seating areas:

```yaml
zone_exclusions:
  bedroom: ["bed_zone"]
  living_room: ["couch_zone", "floor_play_zone"]
```

Zones must be defined in Frigate first (see
[Zone Exclusion Guide](#zone-exclusion-guide) below).

### 4. Reduce Frame Sample Rate

Processing fewer frames per second makes the system less reactive to brief
poses:

```yaml
frame_sample_rate: 1.0  # Down from default 2.0
```

At 1 FPS, a 3-second confirmation window requires 3 consecutive positive
frames. A momentary pose is less likely to hit 3 out of 3.

### 5. Use Per-Camera Overrides

Some cameras may need different thresholds due to their angle or the
activities that occur in their field of view:

```yaml
camera_overrides:
  living_room:
    confidence_threshold: 0.85  # Higher - lots of activity
  hallway:
    confidence_threshold: 0.65  # Lower - simple scene, fewer false positives
```

---

## Reducing Missed Detections

If the system is not detecting real falls (tested with the test alert service
and real scenarios), try these adjustments:

### 1. Lower the Confidence Threshold

```yaml
confidence_threshold: 0.60  # Down from default 0.70
```

Lower in increments of 0.05. Monitor false positives at each level.

### 2. Decrease the Confirmation Time

```yaml
confirmation_seconds: 2.0  # Down from default 3.0
```

A shorter window means falls are detected faster, but brief non-fall poses
are more likely to trigger alerts.

### 3. Increase Frame Sample Rate

```yaml
frame_sample_rate: 3.0  # Up from default 2.0
```

More frames per second means the system has more chances to capture the fall
pose during the confirmation window. Costs more CPU.

### 4. Use the Thunder Model

The Thunder model is more accurate (but slower) than Lightning:

```yaml
pose_model: "thunder"
```

Thunder produces more precise keypoint positions, which improves scoring
accuracy — especially for partially occluded bodies or unusual angles.

### 5. Check Camera Placement

A missed detection is often a camera problem, not a software problem. See
[Camera Placement Tips](#camera-placement-tips) below.

---

## Camera Placement Tips

Camera placement has the biggest impact on detection quality. Poor placement
causes both false positives and missed detections.

### Optimal Camera Position

```
         Camera
         ┌─┐
         │ │  ← Wall-mounted, 2.0–2.5m height
         └─┘
          │    ← 15–30° downward angle
          │
          ▼
    ┌───────────┐
    │           │
    │  Detection│  ← 2–5m from camera
    │   Zone    │
    │           │
    └───────────┘
```

### Height

| Height | Quality | Notes |
|---|---|---|
| < 1.5 m | Poor | Too low; people walk through frame too quickly |
| **2.0–2.5 m** | **Best** | Good overhead angle; full body visible |
| 2.5–3.0 m | Good | Works well in rooms with high ceilings |
| > 3.0 m | Fair | People appear small; keypoint accuracy drops |

### Angle

- **15–30° downward tilt** is ideal. This provides a good view of the full
  body without extreme foreshortening.
- **Straight ahead** (0° tilt) is acceptable but may have occlusion issues
  with furniture.
- **Top-down** (90°) does **not** work. MoveNet is trained on side/front views.

### Field of View

- The **full body** must be visible in the frame when a person is in the
  detection zone. If the camera only captures the upper body, fall scoring
  will be unreliable.
- **Wide-angle lenses** (90–120°) work well for monitoring rooms.
- **Narrow lenses** (< 60°) may miss falls at the edges of the room.

### Distance

- **2–5 meters** from the camera to the monitored area is ideal.
- Closer than 2 m: people are too large in frame, often partially visible.
- Further than 5 m: people are too small; keypoint estimation becomes
  inaccurate.

### Lighting

- **Even, diffused lighting** is best. Avoid strong directional light that
  creates deep shadows.
- The system works in dim conditions if the camera has adequate low-light
  capability.
- **IR night vision** affects detection quality — see
  [Time-of-Day Considerations](#time-of-day-considerations).
- Avoid placing cameras facing windows — backlit subjects are hard to detect.

### Common Placement Mistakes

| Mistake | Problem | Fix |
|---|---|---|
| Camera in corner looking diagonally | Extreme foreshortening; body proportions distorted | Mount on wall center, facing the room |
| Camera too high (ceiling mount) | Top-down view; MoveNet performs poorly | Lower to 2–2.5 m on wall |
| Camera facing a mirror | Detects reflections as separate people | Reposition or mask the mirror zone |
| Camera behind glass | IR reflection; autofocus issues | Mount on the same side as the subject |
| Only upper body visible | Can't assess leg position for fall scoring | Ensure full body is in frame |

---

## Per-Camera Threshold Adjustments

Different cameras may need different settings based on their environment:

```yaml
camera_overrides:
  living_room:
    confidence_threshold: 0.85
    confirmation_seconds: 5.0
  hallway:
    confidence_threshold: 0.65
    confirmation_seconds: 2.0
  kitchen:
    confidence_threshold: 0.75
    confirmation_seconds: 3.0
  bedroom:
    confidence_threshold: 0.70
    confirmation_seconds: 4.0
```

### Guidelines for Per-Camera Tuning

| Camera Location | Suggested Threshold | Suggested Confirmation | Rationale |
|---|---|---|---|
| Hallway/corridor | 0.60–0.70 | 2–3 s | Simple scene, few confounding activities |
| Living room | 0.75–0.85 | 4–5 s | People sit, lie on couches, play with pets |
| Kitchen | 0.70–0.80 | 3–4 s | Bending to pick things up, loading dishwasher |
| Bedroom | 0.70–0.80 | 4–5 s | Getting in/out of bed looks like falling |
| Bathroom | 0.65–0.75 | 3–4 s | High fall risk area; be more sensitive |
| Staircase | 0.60–0.70 | 2–3 s | Falls happen fast; need quick detection |
| Workshop/garage | 0.80–0.90 | 5–6 s | Lots of bending, kneeling, crawling |

---

## Zone Exclusion Guide

Zone exclusions let you ignore specific areas where horizontal postures are
expected and normal.

### Step 1: Define Zones in Frigate

Zones are defined in Frigate's configuration using normalized coordinates
(0.0–1.0):

```yaml
# frigate.yml
cameras:
  bedroom:
    zones:
      bed_zone:
        coordinates: 0.1,0.4,0.7,0.4,0.7,0.95,0.1,0.95
      desk_chair_zone:
        coordinates: 0.75,0.3,0.95,0.3,0.95,0.7,0.75,0.7
  living_room:
    zones:
      couch_zone:
        coordinates: 0.0,0.5,0.4,0.5,0.4,0.9,0.0,0.9
      floor_play_zone:
        coordinates: 0.5,0.6,0.9,0.6,0.9,0.95,0.5,0.95
```

### Step 2: Add Exclusions in Fall Detector

```yaml
# Fall Detector add-on configuration
zone_exclusions:
  bedroom: ["bed_zone", "desk_chair_zone"]
  living_room: ["couch_zone", "floor_play_zone"]
```

### Step 3: Verify

1. Enable debug frames:
   ```yaml
   debug_frames: true
   ```
2. Check the debug output in `/share/fall_detector/debug/` — excluded zones
   should be marked and events within them should show as discarded.
3. Disable debug frames when done:
   ```yaml
   debug_frames: false
   ```

### Common Zones to Exclude

| Zone | Camera | Why |
|---|---|---|
| Bed | Bedroom | Lying in bed = fall-like posture |
| Couch/sofa | Living room | Reclining on couch triggers false positives |
| Floor seating | Living room, playroom | Sitting on floor is normal in some homes |
| Recliner | Living room, bedroom | Reclined position mimics a fall |
| Bathtub | Bathroom | Lying in tub = horizontal posture (but zone this carefully — bathroom falls are common) |
| Pet bed | Any room | Large dogs lying down can trigger person detection in Frigate |

> **Warning:** Be cautious excluding zones in high-risk areas. If you exclude
> the area around a bed, falls **next to** the bed will also be missed if the
> person lands in the excluded zone. Make exclusion zones tight around the
> furniture, not the whole area.

---

## Time-of-Day Considerations

Detection quality can vary between day and night due to camera behavior
changes.

### IR Night Vision Impact

Most home cameras switch to infrared (IR) mode in darkness:

- **Grayscale image**: Pose estimation models are trained primarily on color
  images. Grayscale reduces accuracy slightly.
- **IR artifacts**: Hot spots, reflection halos, and blooming can confuse
  object detection.
- **Reduced contrast**: Dark clothing blends with shadows, making keypoint
  detection harder.

**Recommendations:**

- Use cameras with good IR illumination (multiple IR LEDs, wide coverage).
- Test detection quality specifically at night with debug frames enabled.
- Consider slightly lower thresholds for night hours if missed detections
  increase:
  ```yaml
  # Not yet natively supported as time-based config.
  # Use an HA automation to adjust via the API at night:
  automation:
    - alias: "Lower fall detection threshold at night"
      trigger:
        - platform: time
          at: "22:00:00"
      action:
        - service: rest_command.set_fall_threshold
          data:
            threshold: 0.65
  ```

### Daytime Challenges

- **Direct sunlight**: Strong directional light creates harsh shadows that
  can confuse pose estimation.
- **Backlighting**: A person silhouetted against a bright window is hard to
  analyze.
- **Moving shadows**: Tree shadows or passing cars can create motion artifacts.

---

## Frame Sample Rate Tuning

The `frame_sample_rate` setting controls how many frames per second the
detection pipeline processes. This is independent of Frigate's detect FPS.

### Trade-offs

| FPS | CPU Usage (per camera) | Detection Latency | False Positive Risk |
|---|---|---|---|
| 1.0 | Low | Higher (up to 1s gap) | Lower (fewer samples) |
| **2.0** | **Moderate (default)** | **Moderate** | **Moderate** |
| 3.0 | Moderate-High | Lower | Slightly higher |
| 5.0 | High | Lowest | Higher (more chances to trigger) |

### Guidelines

- **Start with 2.0 FPS** (the default). This works well for most setups.
- **Decrease to 1.0 FPS** if:
  - You are CPU-constrained (RPi 4 with many cameras).
  - You experience high CPU warnings in the add-on logs.
  - Detection latency of 1 second is acceptable.
- **Increase to 3.0+ FPS** if:
  - You have a powerful CPU (x86 mini PC).
  - You need the fastest possible detection response.
  - You monitor high-risk areas (staircases, bathrooms).

### CPU Budget

Rough CPU estimates per camera:

| Model | 1 FPS | 2 FPS | 5 FPS |
|---|---|---|---|
| Lightning (RPi 4) | ~3% | ~6% | ~15% |
| Lightning (x86 N100) | ~1% | ~2% | ~5% |
| Thunder (RPi 4) | ~8% | ~15% | ~40% |
| Thunder (x86 N100) | ~3% | ~5% | ~12% |

---

## Pose Backend Selection

The add-on supports two MoveNet variants:

### Lightning (Default)

- **Input size**: 192×192 pixels
- **Speed**: ~15 ms per frame (x86), ~50 ms (RPi 4)
- **Accuracy**: Good — sufficient for most fall detection scenarios
- **Best for**: RPi 4, multiple cameras, CPU-constrained systems

### Thunder

- **Input size**: 256×256 pixels
- **Speed**: ~35 ms per frame (x86), ~130 ms (RPi 4)
- **Accuracy**: Better — more precise keypoint locations
- **Best for**: x86 systems, single camera setups, difficult camera angles

### When to Use Thunder

- You are getting missed detections with Lightning.
- The camera angle is challenging (partially occluded views, far distance).
- You have a capable CPU and are monitoring 1–2 cameras.
- You need the best possible accuracy and latency is less important.

### When to Stick with Lightning

- You are monitoring 3+ cameras.
- You are running on a Raspberry Pi 4.
- Lightning is producing acceptable results.
- CPU usage is a concern.

---

## Common False Positive Scenarios

| Scenario | Why It Triggers | Solution |
|---|---|---|
| **Bending to pick something up** | Torso becomes near-horizontal briefly | Increase `confirmation_seconds` to 4–5 s |
| **Tying shoes / petting a pet** | Low crouching posture for several seconds | Increase `confirmation_seconds` to 5+ s |
| **Lying on couch** | Horizontal body posture | Add couch zone to `zone_exclusions` |
| **Getting into/out of bed** | Transitional posture passes through fall-like angles | Add bed zone to `zone_exclusions`; increase `confirmation_seconds` |
| **Yoga / exercise** | Many fall-like poses | Mute the camera during exercise times; increase threshold |
| **Playing with children on floor** | Adult in horizontal position on floor | Add play zone exclusion; increase threshold |
| **Dropped object + reaching** | Person leans far over, high torso angle | Increase `confidence_threshold` |
| **Sitting on low furniture** | Low seat height + leaning = fall-like score | Increase threshold for that camera |
| **Wheelchair user transferring** | Transitional posture during transfers | Higher threshold + longer confirmation for that camera |
| **Large dog detected as person** | Frigate misclassifies large dog | Improve Frigate object detection; use Coral TPU |
| **Shadow / reflection** | Mirror or shadow creates ghost person | Mask the mirror zone in Frigate |
| **Camera vibration / shake** | Sudden frame shift creates pose artifacts | Mount camera more securely; reduce FPS |

---

## Logging for Debugging

### Enable Debug Logging

Set the log level in the add-on configuration:

```yaml
log_level: "debug"
```

Debug logging outputs:

- Every Frigate event received (with filter decisions).
- Every frame fetch (with timing).
- Every pose estimation result (keypoints, scores).
- Every fall score computation (per-feature breakdown).
- Confirmation state machine transitions.
- Alert decisions (publish, suppress due to mute/cooldown).

### Enable Debug Frames

Debug frames are annotated images saved to disk showing:

- The detected person bounding box
- Pose skeleton overlay
- Keypoint confidence values
- Computed fall score
- Confirmation state
- Zone exclusion boundaries

```yaml
debug_frames: true
```

Frames are saved to `/share/fall_detector/debug/{camera}/{timestamp}.jpg`.

> **Warning:** Debug frames consume significant disk space (each frame is
> ~50–200 KB). At 2 FPS with 3 cameras, that is ~1–3 GB per day. Enable
> only for tuning sessions, then disable.

### Viewing Logs

**Add-on logs:**

1. Go to **Settings → Add-ons → Fall Detector → Log**.
2. Or via SSH:
   ```bash
   docker logs addon_local_fall_detector -f --tail 200
   ```

**Integration logs:**

1. Add to `configuration.yaml`:
   ```yaml
   logger:
     logs:
       custom_components.fall_detector: debug
   ```
2. Restart HA.
3. View in **Settings → System → Logs**.

---

## Iterative Tuning Workflow

Follow this process to systematically tune your setup:

### Phase 1: Baseline (Days 1–3)

1. Install with default settings.
2. Enable `debug_frames: true` and `log_level: "debug"`.
3. Live normally — go about regular activities in monitored areas.
4. At the end of each day, check:
   - How many false positive alerts were generated?
   - Were any real falls missed (if tested)?
   - What activities caused false positives?

### Phase 2: Reduce False Positives (Days 4–7)

5. Review debug frames for false positives.
6. Identify the cause for each (bending, couch, bed, etc.).
7. Apply the most appropriate fix:
   - Zone exclusion for furniture-related triggers.
   - Increase threshold for activity-related triggers.
   - Increase confirmation time for brief postures.
8. Test again for a few days.

### Phase 3: Validate Detection (Days 8–10)

9. With reduced false positives, verify falls are still detected:
   - Use `fall_detector.test_alert` service to test the notification pipeline.
   - **Safe physical test**: In a clear area with padding/mats, slowly lower
     yourself to the ground in a controlled manner. Do **not** fall
     uncontrolled for testing.
   - Check debug frames for the test — was the fall scored correctly?
10. If detection sensitivity is too low, selectively lower thresholds.

### Phase 4: Production (Ongoing)

11. Disable `debug_frames` to save disk space.
12. Set `log_level: "info"`.
13. Monitor for false positives over time.
14. Re-tune seasonally (lighting changes with seasons can affect detection).
