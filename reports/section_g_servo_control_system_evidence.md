# Section G - Servo Control System

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

Secondary context checked (limited direct servo evidence):
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/SETUP.md](../docs/SETUP.md)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Historical behavior is reconstructed from reports/log docs.
- Any statement that is not directly explicit in code/docs is marked as INFERENCE.

---

## G1. Servo Hardware Integration (Pan/Tilt System)

### Technical evidence summary

The hardware layer is implemented as a Pi-side actuator daemon:
- Pan/Tilt channels are mapped to dedicated GPIO pins (`PAN_PIN = 18`, `TILT_PIN = 19`): [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 14-15.
- Mechanical limits are software-enforced (`MIN_ANGLE = 20`, `MAX_ANGLE = 160`): [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 16-17.
- Actuation is produced through `pigpio` pulse-width output: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 8, 26, 35-38.
- Service startup fails if `pigpiod` is unavailable: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) line 28.

The physical motivation is explicitly documented as a 2-DOF pan/tilt re-orientation mechanism for face recentering: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 5-7.

### 1. What existed before

- INFERENCE: Prior runtime could function without servo hardware because servo is feature-gated and defaults off (`SERVO_ENABLED = False`): [app/config.py](../app/config.py) line 258.
- Runtime explicitly supports disabled mode (`Servo Control DISABLED`): [app/main.py](../app/main.py) line 462.

### 2. What changed

- Pi-side actuator service was added with explicit pan/tilt mapping, limit clamping, and pulse output: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 14-18, 64-84.
- Host startup now conditionally creates `ServoController` using configured Pi endpoint: [app/main.py](../app/main.py) lines 458-460.
- Servo env knobs were centralized in config (`SV_SERVO_*`): [app/config.py](../app/config.py) lines 258-265.

### 3. Why it changed

- To physically adjust camera orientation from detection results instead of only drawing overlays/logging detections.
- This design intent is explicit in the technical report: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 5-7.

### 4. What files matter most

- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful snippets

Snippet G1-1 from [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

~~~python
PAN_PIN = 18
TILT_PIN = 19
MIN_ANGLE = 20
MAX_ANGLE = 160
STEP_SIZE = 1  # Degrees per command
~~~

Snippet G1-2 from [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

~~~python
pi = pigpio.pi()
if not pi.connected:
    print("Error: Could not connect to pigpiod. Is the daemon running? (sudo pigpiod)")
    exit(1)
~~~

Snippet G1-3 from [app/main.py](../app/main.py)

~~~python
if config.SERVO_ENABLED:
    log.info("Servo Control ENABLED - Target Pi: %s:%d", config.SERVO_PI_IP, config.SERVO_PI_PORT)
    servo_controller = ServoController(config.SERVO_PI_IP, config.SERVO_PI_PORT)
else:
    log.info("Servo Control DISABLED (via config)")
~~~

### 6. How to describe this in report language

- The project extends from software-only perception to cyber-physical operation by integrating a Pi-based PWM actuator layer with constrained pan/tilt ranges and explicit runtime feature gating.
- Pan and tilt are independently addressable channels, allowing coarse 2-axis camera recentering under software control.

### 7. Limitations / honest weaknesses

- GPIO pins and angle bounds are hardcoded in script constants: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 14-18.
- Requires `pigpiod` daemon and Pi-specific setup; package/install friction is documented: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 52-58.
- Port conflict risk around Pi services is documented (pigpiod and MediaMTX): [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 62-64.
- INFERENCE: No calibration persistence (servo zero-offset tuning) is visible in current code/docs.

---

## G2. Distributed Servo Control Architecture

### Technical evidence summary

The implementation is explicitly split across host and Pi:
- Host/Laptop: detection + control decision logic (`ServoController`) in [app/services/servo_service.py](../app/services/servo_service.py) and integration in [app/main.py](../app/main.py) lines 188-193.
- Pi: command receiver + PWM actuator in [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 53-84.
- Transport split by protocol:
  - RTSP for video ingest: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 27.
  - HTTP for control command dispatch: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 28.

### 1. What existed before

- Baseline system origin was local-webcam ingestion: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) line 5.
- INFERENCE: No remote actuator channel was active in the baseline because current servo dispatch is behind `SERVO_ENABLED` and Pi endpoint setup.

### 2. What changed

- Architecture evolved to remote-edge camera/actuator with host-side ML and control decision.
- Documentation now explicitly describes host/client role separation: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 14-23.

### 3. Why it changed

- To support deployment decoupling: Pi near camera, host for heavier processing.
- Host as more powerful processor is stated in RTSP integration notes: [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) lines 13-14.

### 4. What files matter most

- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [app/main.py](../app/main.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

### 5. Useful snippets

Snippet G2-1 from [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

~~~text
Host (Laptop): Performs face detection, computes position, applies control logic, sends movement commands.
Client (Raspberry Pi): Receives commands via HTTP API, generates PWM using pigpio, actuates servos.
Protocols: RTSP (video), HTTP (control).
~~~

Snippet G2-2 from [app/main.py](../app/main.py)

~~~python
if config.SERVO_ENABLED and servo_controller is not None and result.primary_detection:
    servo_controller.compute_and_send(
        result.primary_detection,
        frame.shape[1],
        frame.shape[0]
    )
~~~

Snippet G2-3 from [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

~~~text
Laptop ServoController -> HTTP /move -> Pi Flask Service -> PWM -> GPIO 18/19 Servos
~~~

### 6. How to describe this in report language

- The control loop is intentionally distributed: perception and policy stay on the host, while low-level actuation runs at the edge node.
- This reduces hardware burden on the Pi and preserves integration with the existing host ML pipeline.

### 7. Limitations / honest weaknesses

- No durable command queue/ack protocol is present; control is best-effort request/response.
- If network/Pi is unavailable, command send fails and returns false without higher-level compensation: [app/services/servo_service.py](../app/services/servo_service.py) lines 162-170.
- INFERENCE: The architecture is robust enough for LAN prototype use but not fault-tolerant for mission-critical distributed control.

---

## G3. Latency Impact on Control Systems

### Technical evidence summary

Measured RTSP overhead materially changes feedback conditions:
- Camera FPS: 30.0 -> 15.0
- Read time: 27.4 ms -> 52.0 ms
- Max pipeline latency: 141.0 ms -> 266.0 ms
- ML FPS: 10.0 -> 5.0
Evidence: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 34-40.

Observed delay is larger than internal pipeline timings due in-flight buffering/transport:
- Observed network ingestion delay ~0.5-1.5s: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) line 54.
- RTSP camera notes also state 0.3-1.5s typical LAN latency and backend buffering constraints: [app/camera/rtsp.py](../app/camera/rtsp.py) lines 12-17.

### 1. What existed before

- Webcam baseline had lower latency/higher throughput and therefore tighter apparent feedback behavior: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 34-40.

### 2. What changed

- RTSP deployment introduced decode/network delay and lower temporal resolution of feedback frames.
- Runtime diagnostics from RTSP runs show sustained ~15 fps ingest with variable max latency spikes: [new_rtsp_main.txt](../new_rtsp_main.txt) lines 405, 461.

### 3. Why it changed

- Because `cv2.VideoCapture.read()` on RTSP carries demux/decode overhead and buffering behavior.
- This bottleneck is directly called out in evaluation analysis: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) line 49.

### 4. What files matter most

- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

### 5. Useful snippets

Snippet G3-1 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
| Avg Camera FPS      | 30.0 fps | 15.0 fps |
| Avg Frame Read Time | 27.4 ms  | 52.0 ms  |
| Max Pipeline Latency| 141.0 ms | 266.0 ms |
| ML FPS              | 10.0 fps | 5.0 fps  |
~~~

Snippet G3-2 from [app/camera/rtsp.py](../app/camera/rtsp.py)

~~~text
Typical end-to-end latency over a local LAN: 0.3-1.5 seconds.
This is inherent to the RTSP/TCP/H.264 decode pipeline and cannot be fully eliminated
without replacing the capture backend.
~~~

Snippet G3-3 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~text
When an RTSP stream dies mid-connection, cv2.VideoCapture.read() may block
for several seconds; during this time the fast loop in main.py is paused.
~~~

### 6. How to describe this in report language

- RTSP-induced latency degrades the freshness of visual feedback, so control decisions operate on delayed observations rather than near-current state.
- This delay profile justifies stability-first control constraints (cooldown, dead zone, lockout) over aggressive continuous pursuit.

### 7. Limitations / honest weaknesses

- Host-side metrics do not fully represent user-perceived glass-to-glass delay: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 54, 64-65.
- Best-effort low-latency flags are backend-dependent hints and may be ignored: [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) lines 147-151.
- INFERENCE: Latency variance, not only mean latency, is likely a major oscillation driver, but variance decomposition is not separately quantified.

---

## G4. Step-Wait Control Strategy Design

### Technical evidence summary

The controller is explicitly described as Step-Wait / step-based recentering:
- Class docstring: "Implements Step-Wait logic to handle RTSP delay": [app/services/servo_service.py](../app/services/servo_service.py) line 9.
- Technical report: "step-based re-centering strategy rather than continuous tracking": [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 7.

Mechanics:
- Per-command cooldown gate (`SERVO_COOLDOWN_MS`, default 500 ms): [app/services/servo_service.py](../app/services/servo_service.py) line 21, [app/config.py](../app/config.py) line 264.
- Fixed small Pi actuator increment (`STEP_SIZE = 1` degree per command): [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) line 18.

### 1. What existed before

- INFERENCE: A continuous frame-by-frame actuation strategy was considered undesirable under delayed RTSP feedback.
- Report explicitly contrasts final strategy against continuous tracking: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 7.

### 2. What changed

- Command generation now passes through global cooldown suppression before any move is issued: [app/services/servo_service.py](../app/services/servo_service.py) lines 54-56.
- System moved to discrete command cadence instead of unrestricted command stream.

### 3. Why it changed

- To avoid issuing multiple commands on stale frames under RTSP delay.
- Cooldown rationale is explicitly documented as latency compensation: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 127-129.

### 4. What files matter most

- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [app/config.py](../app/config.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful snippets

Snippet G4-1 from [app/services/servo_service.py](../app/services/servo_service.py)

~~~python
self.cooldown_period = config.SERVO_COOLDOWN_MS / 1000.0

if now - self.last_command_time < self.cooldown_period:
    self.logger.debug("SERVO_SUPPRESS [COOLDOWN] ...")
    return False
~~~

Snippet G4-2 from [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

~~~python
STEP_SIZE = 1  # Degrees per command
~~~

Snippet G4-3 from [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

~~~text
Due to RTSP latency (approximately 300ms-800ms), design prioritises stability
and robustness over real-time responsiveness.
~~~

### 6. How to describe this in report language

- Step-Wait is a latency-aware control simplification: each correction step is followed by an enforced wait to let scene feedback catch up before issuing another command.
- This intentionally trades responsiveness for predictable behavior.

### 7. Limitations / honest weaknesses

- Fixed cooldown can under-react during fast motion and over-react during calm scenes.
- Coarse discrete steps cannot provide smooth tracking trajectories.
- Config mismatch risk: `SERVO_STEP_DEGREES` exists in config but no usage was found beyond definition, while Pi uses hardcoded `STEP_SIZE = 1`: [app/config.py](../app/config.py) line 263 and [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) line 18.

---

## G5. Dead Zone and Anti-Oscillation Control Logic

### Technical evidence summary

Dead zone geometry:
- Dead zone ratio from config (`SERVO_DEADZONE_RATIO`, default 0.35): [app/config.py](../app/config.py) line 262.
- Bounds are centered around 0.5 normalized center:
  - `dead_zone_min = 0.5 - half_zone`
  - `dead_zone_max = 0.5 + half_zone`
  Evidence: [app/services/servo_service.py](../app/services/servo_service.py) lines 24-27.

Anti-oscillation:
- Opposite-direction lockout uses `SERVO_OPPOSITE_LOCKOUT_MS` (default 1200 ms): [app/config.py](../app/config.py) line 265 and [app/services/servo_service.py](../app/services/servo_service.py) line 22.
- Reversal is blocked unless error is "extreme" (`<0.15` or `>0.85`): [app/services/servo_service.py](../app/services/servo_service.py) lines 31-32, 141-147.

### 1. What existed before

- INFERENCE: Without these guards, delayed feedback would produce jitter near center and rapid direction flipping at boundaries.

### 2. What changed

- Added dead-zone suppression path and explicit suppression logging: [app/services/servo_service.py](../app/services/servo_service.py) lines 102-106.
- Added reversal lockout with emergency override for large error: [app/services/servo_service.py](../app/services/servo_service.py) lines 133-147.

### 3. Why it changed

- To stabilize recentering under RTSP delay, explicitly documented under dead zone/cooldown/anti-oscillation sections: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 122-133.

### 4. What files matter most

- [app/services/servo_service.py](../app/services/servo_service.py)
- [app/config.py](../app/config.py)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful snippets

Snippet G5-1 from [app/services/servo_service.py](../app/services/servo_service.py)

~~~python
half_zone = self.dead_zone_ratio / 2
self.dead_zone_min = 0.5 - half_zone
self.dead_zone_max = 0.5 + half_zone
~~~

Snippet G5-2 from [app/services/servo_service.py](../app/services/servo_service.py)

~~~python
if target_dir == last_dir:
    return True

is_extreme = normalized_val < self.extreme_threshold_min or normalized_val > self.extreme_threshold_max
if is_extreme:
    return True

self.logger.info("SERVO_SUPPRESS [OSCILLATION] ...")
return False
~~~

Snippet G5-3 from [tests/test_servo_logic.py](../tests/test_servo_logic.py)

~~~python
def test_anti_oscillation_block(controller):
    ...
    moved = controller.compute_and_send(face_right, 640, 480)
    assert moved is False

def test_anti_oscillation_override_extreme(controller):
    ...
    moved = controller.compute_and_send(face_extreme_right, 640, 480)
    assert moved is True
~~~

### 6. How to describe this in report language

- The controller uses both spatial hysteresis (dead zone) and directional hysteresis (opposite-lockout window) to reject unstable command chatter while preserving recovery when face error becomes critical.

### 7. Limitations / honest weaknesses

- Thresholds are static and scene-dependent; no adaptive tuning logic is present.
- INFERENCE: Different camera FOV or mounting geometry likely requires retuning dead zone and extreme thresholds.
- Axis scheduling prioritizes pan over tilt in each decision cycle, which can delay vertical correction: [app/services/servo_service.py](../app/services/servo_service.py) lines 85-87.

---

## G6. HTTP-Based Remote Actuation System

### Technical evidence summary

Pi-side HTTP API design:
- Endpoint `/move` consumes `axis` and `dir` query params: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 53, 57-58.
- Missing args return HTTP 400: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 60-61.
- Successful movement returns JSON with new angle; invalid combinations return 400/no_change: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 86-92.

Host dispatch:
- Sends `GET /move` with timeout 1.0 s: [app/services/servo_service.py](../app/services/servo_service.py) line 159.
- Handles timeout/connection/HTTP errors with logs and false return: [app/services/servo_service.py](../app/services/servo_service.py) lines 162-170.

### 1. What existed before

- INFERENCE: No explicit remote actuation API existed before servo enhancement because current control depends on newly introduced Pi service and host request path.

### 2. What changed

- Introduced stateless LAN HTTP control channel between host and Pi.
- Added lightweight status endpoint exposing pan/tilt/min/max: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) lines 44-51.

### 3. Why it changed

- To keep integration simple and debuggable during FYP implementation while decoupling ML host from hardware actuator code.
- This command interface is directly documented in the technical report: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 97.

### 4. What files matter most

- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [app/config.py](../app/config.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful snippets

Snippet G6-1 from [app/services/servo_service.py](../app/services/servo_service.py)

~~~python
url = f"{self.base_url}/move"
params = {"axis": axis, "dir": direction}
resp = requests.get(url, params=params, timeout=1.0)
~~~

Snippet G6-2 from [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

~~~python
axis = request.args.get('axis', '').lower()
direction = request.args.get('dir', '').lower()

if not axis or not direction:
    return jsonify({"error": "Missing axis or dir"}), 400
~~~

Snippet G6-3 from [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

~~~python
app.run(host='0.0.0.0', port=5000, debug=False)
~~~

### 6. How to describe this in report language

- The actuation layer uses a minimal HTTP command protocol with explicit input validation and bounded state transitions, enabling clean host-Pi separation without custom binary protocols.

### 7. Limitations / honest weaknesses

- Endpoint is exposed on all interfaces and not authenticated: [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) line 100 and [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 212.
- Uses GET for side effects (movement), which is pragmatic but not strict REST semantics.
- No retry/backoff policy at send layer beyond per-frame control loop attempts.

---

## G7. Latency-Tolerant Face Re-Centering System

### Technical evidence summary

End-to-end recentering path:
1) Detection enters slow processing loop.
2) If servo enabled and `primary_detection` exists, host computes control decision.
3) Host sends remote move to Pi.
4) Pi updates servo angle and outputs PWM.

Code anchors:
- Integration gate and call: [app/main.py](../app/main.py) lines 188-193.
- Face center extraction and normalization: [app/services/servo_service.py](../app/services/servo_service.py) lines 61-66.
- Pan-first decision and optional tilt fallback: [app/services/servo_service.py](../app/services/servo_service.py) lines 72-99.

### 1. What existed before

- INFERENCE: Primary face detection already existed for recognition/event logic, but no mandatory physical recentering path was active when servo disabled.

### 2. What changed

- Physical recentering got integrated directly into the slow ML loop using `result.primary_detection`: [app/main.py](../app/main.py) line 188.
- Controller now operates on normalized frame coordinates to keep behavior resolution-independent: [app/services/servo_service.py](../app/services/servo_service.py) lines 65-66.

### 3. Why it changed

- To produce practical camera recentering under delayed RTSP feedback instead of attempting high-bandwidth real-time tracking.
- Explicitly stated as "latency-tolerant" and "step-based": [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 5-7.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful snippets

Snippet G7-1 from [app/main.py](../app/main.py)

~~~python
if config.SERVO_ENABLED and servo_controller is not None and result.primary_detection:
    servo_controller.compute_and_send(
        result.primary_detection,
        frame.shape[1],
        frame.shape[0]
    )
~~~

Snippet G7-2 from [app/services/servo_service.py](../app/services/servo_service.py)

~~~python
bbox = face_bbox.bbox
center_x, center_y = bbox.center
center_x = center_x / frame_w
center_y = center_y / frame_h
~~~

Snippet G7-3 from [app/services/servo_service.py](../app/services/servo_service.py)

~~~python
# We prioritize horizontal correction to avoid simultaneous axis noise,
# but check Tilt if Pan didn't trigger.
if not cmd_axis:
    ...
~~~

### 6. How to describe this in report language

- The system performs coarse closed-loop recentering by selecting one axis correction from the current primary face estimate, applying suppression rules, and dispatching a remote actuator command.
- This is a robust recentering approach for delayed feedback, not a smooth tracking controller.

### 7. Limitations / honest weaknesses

- Single-target behavior (primary/largest face) is an explicit system limit: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 211.
- Discrete movements are explicitly acknowledged; no smooth continuous tracking: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 208.
- INFERENCE: There is no motion prediction or trajectory model; decisions are reactive to current delayed frame only.

---

## G8. Control System Evaluation Under RTSP Latency

### Technical evidence summary

Evaluation combines benchmark docs, runtime logs, and tuning notes:
- Controlled webcam-vs-RTSP comparison: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 34-40.
- Runtime diagnostics confirming RTSP operating envelope (about 15 fps ingest, about 5 fps ML): [new_rtsp_main.txt](../new_rtsp_main.txt) lines 405-406.
- MJPEG-side diagnostics show around 6.6-7.8 fps yields with stale frame counts and latency spikes: [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt) lines 23-33.
- Aggressive tuning profile tested but flagged as oscillation-prone: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 153-164.

### 1. What existed before

- Prior evaluations focused on ingestion/latency behavior and baseline pipeline stability.
- Historical servo-specific testing narrative is documented in the dedicated technical report rather than in BUILD_LOG/ARCHITECTURE.

### 2. What changed

- Servo design decisions were tied to measured RTSP constraints and field observations.
- Technical report records field issues and fixes:
  - Vertical movement inverted -> mapping corrected.
  - Invalid axis/dir combinations -> validation improved.
  - Attribute access error -> bbox reference fixed.
  Evidence: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 181-187.

### 3. Why it changed

- To establish practical viability under real RTSP delay/jitter and avoid unstable motion behavior.
- Aggressive profile evidence directly shows responsiveness vs oscillation trade-off: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 164.

### 4. What files matter most

- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

### 5. Useful snippets

Snippet G8-1 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
Network Ingestion Delay (Observed ~0.5s - 1.5s) is responsible for visual lag,
even when host-side pipeline latency appears moderate.
~~~

Snippet G8-2 from [new_rtsp_main.txt](../new_rtsp_main.txt)

~~~text
[DIAG FAST] cam=15.0 fps (avg=52.0ms max=79.0ms) ...
[DIAG SLOW] ... ml=5.1 fps
~~~

Snippet G8-3 from [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

~~~text
Aggressive tuning result: faster response but significantly increased risk of
mechanical oscillation; treated as experimental.
~~~

### 6. How to describe this in report language

- Evaluation indicates the servo extension is viable as a stability-focused recentering system in LAN RTSP deployments, provided control policy remains conservative.
- The evidence supports engineering compromise: reduced responsiveness is accepted to prevent oscillation and command thrash under delayed feedback.

### 7. Limitations / honest weaknesses

- No formal closed-loop control metrics (settling time, overshoot, command-rate spectrum) are reported.
- Runtime logs include repeated FFmpeg VideoWriter codec initialization errors in some runs: [new_rtsp_main.txt](../new_rtsp_main.txt) lines 55, 57.
- Test/docs consistency caution:
  - Technical report claims full servo logic coverage and passing tests: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 178.
  - INFERENCE: Current `tests/test_servo_logic.py` appears to pass a bare `BBox` object into `compute_and_send`, while `ServoController` currently dereferences `face_bbox.bbox` in code; execution status was not verified in this evidence pass.

---

## Layer Separation Checklist (for final writing stage)

Hardware layer evidence:
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) (GPIO pins, angles, pigpio)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) (setup constraints)

Network actuation layer evidence:
- [app/services/servo_service.py](../app/services/servo_service.py) (`requests.get` `/move`, timeout/error handling)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) (`/move` parsing, validation, state update)

Control logic layer evidence:
- [app/services/servo_service.py](../app/services/servo_service.py) (dead zone, cooldown, lockout, extreme override)
- [app/config.py](../app/config.py) (`SV_SERVO_*` defaults)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py) (intended control rule tests)

Evaluation/feasibility layer evidence:
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)