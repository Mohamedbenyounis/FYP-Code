# Section F - Hardware and Distributed Systems

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)
- [app/web_run.py](../app/web_run.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/SETUP.md](../docs/SETUP.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [rtsp_test_log.txt](../rtsp_test_log.txt)
- [webcam_test_log.txt](../webcam_test_log.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

Evidence reliability rule used:
- Current code is ground truth for current runtime behavior.
- Historical behavior and rollout sequence are reconstructed from iteration logs and evaluation reports.
- Any statement that is not explicit in source text is marked as INFERENCE.

---

## F1. Raspberry Pi Camera Deployment Architecture

### Technical evidence summary

Deployed split is camera-at-edge, processing-at-host:
- Host runtime chooses source by `SV_CAMERA_TYPE` and creates `RTSPCamera` or `WebcamCamera` in [app/main.py](../app/main.py).
- RTSP URL is required when `SV_CAMERA_TYPE=rtsp`; startup fails fast if missing in [app/main.py](../app/main.py).
- Camera parameters are centralized as `SV_CAMERA_TYPE`, `SV_CAMERA_INDEX`, `SV_RTSP_URL` in [app/config.py](../app/config.py).

Pi responsibilities (documented):
- Pi runs camera capture and RTSP publishing stack (`rpicam-vid` + `ffmpeg` + MediaMTX) in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).
- Optional Pi servo endpoint exists in [scripts/pi_servo_service.py](../scripts/pi_servo_service.py) and is referenced by [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md).

Host responsibilities (implemented in app code):
- Host reads RTSP stream, runs ML, eventing, DB writes, dashboard shared-memory streaming in [app/main.py](../app/main.py), [app/web/routes.py](../app/web/routes.py), and [app/web_run.py](../app/web_run.py).
- Host-side servo logic computes movement decisions and sends HTTP commands to Pi in [app/services/servo_service.py](../app/services/servo_service.py).

Camera module and deployment assumptions:
- `Raspberry Pi Camera Module v3` is explicit in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) and [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md).
- Recommended baseline is 640x480 at 15 FPS, H.264, RTSP over TCP in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).

### 1. What existed before

Before RTSP deployment support:
- System was webcam-first/local-first (Iteration 1) in [docs/BUILD_LOG.md](../docs/BUILD_LOG.md).
- Architecture document overview still states USB webcam-centric wording in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
- Setup guide prerequisites still list webcam and do not present RTSP/Pi-first setup in [docs/SETUP.md](../docs/SETUP.md).

### 2. What changed

Bonus RTSP iteration introduced distributed camera-host deployment:
- `CameraSource` contract expanded with mandatory `reconnect()` in [app/camera/base.py](../app/camera/base.py).
- New RTSP adapter with FFmpeg backend and retry behavior in [app/camera/rtsp.py](../app/camera/rtsp.py).
- Runtime source selection and reconnect orchestration wired in [app/main.py](../app/main.py).
- Pi-side setup and host env configuration documented in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).

### 3. Why it changed

Explicit motivation:
- Physical decoupling of sensor placement (Pi camera) from compute host for realistic surveillance deployment in [docs/BUILD_LOG.md](../docs/BUILD_LOG.md).
- Evaluation report confirms local webcam constrained deployment flexibility and RTSP was added for edge-sensor topology in [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md).

Why Pi is edge sensor, not processing node:
- Host runs all heavy ML and event processing in [app/main.py](../app/main.py).
- RTSP integration doc future section explicitly lists Pi-side local processing as out of scope in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/config.py](../app/config.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful snippets

Snippet F1-1 from [app/main.py](../app/main.py)

~~~python
camera_type = config.CAMERA_TYPE.strip().lower()
log.info("Camera source: %s", camera_type)

if camera_type == "rtsp":
    if not config.RTSP_URL:
        log.error(
            "CAMERA_TYPE is 'rtsp' but SV_RTSP_URL is empty - "
            "set SV_RTSP_URL to the stream address and retry."
        )
        conn.close()
        return 1
    camera = RTSPCamera(config.RTSP_URL)
else:
    camera = WebcamCamera(device_index=config.CAMERA_INDEX)
~~~

Snippet F1-2 from [app/config.py](../app/config.py)

~~~python
CAMERA_TYPE: str = _env("SV_CAMERA_TYPE", "webcam")
CAMERA_INDEX: int = _env_int("SV_CAMERA_INDEX", 0)
RTSP_URL: str = _env("SV_RTSP_URL", "")

SERVO_ENABLED: bool = _env_bool("SV_SERVO_ENABLED", False)
SERVO_PI_IP: str = _env("SV_SERVO_PI_IP", "172.20.10.5")
SERVO_PI_PORT: int = _env_int("SV_SERVO_PI_PORT", 5000)
~~~

Snippet F1-3 from [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

~~~python
@app.route('/move', methods=['GET'])
def move_servo():
    axis = request.args.get('axis', '').lower()
    direction = request.args.get('dir', '').lower()
    ...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
~~~

### 6. How to describe this in report language

- SecureVision adopts a distributed edge-sensing architecture where Raspberry Pi handles capture/stream serving (and optional actuator endpoint), while the host machine executes compute-heavy ML, event persistence, and dashboard delivery.
- The camera source abstraction preserves one frame-consumption contract (`CameraSource`) so distributed deployment is a source swap, not a pipeline rewrite.

### 7. Limitations and honest weaknesses

- SecureVision does not include RTSP server provisioning; Pi-side stream stack is an external prerequisite in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).
- Current app runtime is single-camera selection (`webcam` or one `rtsp` URL), not multi-stream orchestration.
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) and [docs/SETUP.md](../docs/SETUP.md) contain webcam-centric text that lags bonus RTSP deployment details.
- INFERENCE: Pi is intentionally treated as a capture/control endpoint partly to keep ONNX inference and SQLite consistency on one host process boundary (supported by current code placement, not by an explicit ADR file).

---

## F2. RTSP Server Setup and MediaMTX Integration

### Technical evidence summary

Streaming setup expectations:
- SecureVision consumes but does not host RTSP; Pi must expose RTSP endpoint in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).
- Recommended server is MediaMTX with `rpicam-vid` piped into `ffmpeg` RTSP publish in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).
- Default endpoint shape: `rtsp://<PI_IP>:8554/cam` (MediaMTX option) in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).

Transport and decode handling in SecureVision:
- RTSP path forces OpenCV FFmpeg backend and sets low-latency FFmpeg hints (`rtsp_transport;tcp`, `fflags;nobuffer`, `flags;low_delay`) in [app/camera/rtsp.py](../app/camera/rtsp.py).
- CAP_PROP_BUFFERSIZE is attempted but treated as best-effort in [app/camera/rtsp.py](../app/camera/rtsp.py).
- Reconnect attempts default to 5 attempts with 2s delays in [app/camera/rtsp.py](../app/camera/rtsp.py).

Observed runtime evidence:
- RTSP stream open and diagnostic stabilization are visible in [rtsp_test_log.txt](../rtsp_test_log.txt) and [new_rtsp_main.txt](../new_rtsp_main.txt).
- Live MJPEG diagnostics in [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt) show stream yield around 6.6-7.8 FPS during RTSP runs.

### 1. What existed before

Before RTSP integration:
- Camera path was local webcam through OpenCV without network stream server dependency (Iteration 1 baseline in [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)).
- No Pi-side RTSP setup guidance existed in repo docs before `RTSP_INTEGRATION_LOG.md`.

### 2. What changed

- Added explicit RTSP camera adapter and reconnect behavior in [app/camera/rtsp.py](../app/camera/rtsp.py).
- Added startup config gate (`SV_CAMERA_TYPE=rtsp` requires `SV_RTSP_URL`) in [app/main.py](../app/main.py).
- Added setup/troubleshooting guide for MediaMTX, alternative `v4l2rtspserver`, and validation commands in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).
- Added RTSP test coverage in [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py) and resilience tests in [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py).

### 3. Why it changed

- To support practical deployment where camera is remote from host while keeping host processing stack unchanged.
- To make RTSP failure behavior deterministic (retry loop then clean exit) instead of silent stalls.

### 4. What files matter most

- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py)
- [rtsp_test_log.txt](../rtsp_test_log.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

### 5. Useful snippets

Snippet F2-1 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~bash
# Start the server (default port 8554)
./mediamtx &

# Stream the Pi camera into MediaMTX
rpicam-vid -t 0 --width 640 --height 480 --framerate 15 --codec h264 \
  --inline -o - | ffmpeg -i - -c copy -f rtsp rtsp://localhost:8554/cam
~~~

Snippet F2-2 from [app/camera/rtsp.py](../app/camera/rtsp.py)

~~~python
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp|analyzeduration;0|probesize;32|"
    "fflags;nobuffer|flags;low_delay|framedrop;1"
)

self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
result = self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
~~~

Snippet F2-3 from [new_rtsp_main.txt](../new_rtsp_main.txt) and [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

~~~text
new_rtsp_main.txt:13 Opening RTSP stream: rtsp://FYP-Camera1:8554/cam
new_rtsp_main.txt:14 RTSP stream opened: url=rtsp://FYP-Camera1:8554/cam  resolution=640x360
new_rtsp_main.txt:26 [DIAG FAST] cam=15.0 fps ... enc=7.4 fps ...
new_rtsp_mjpeg.txt:23 [DIAG MJPEG] yield=7.8 fps | stale=85 | err=0 ...
~~~

### 6. How to describe this in report language

- MediaMTX integration is an externalized stream-ingest contract: Pi publishes H.264 RTSP, SecureVision consumes through a fault-tolerant adapter with low-latency hints and reconnect control.
- Transport choices are explicit and conservative (`RTSP over TCP`) to prioritize reliability and deterministic behavior over best-case minimum jitter.

### 7. Limitations and honest weaknesses

- RTSP support depends on external Pi stack health (MediaMTX/ffmpeg/rpicam-vid); SecureVision only reports open/read/reconnect outcomes.
- `CAP_PROP_BUFFERSIZE` and FFmpeg options are hints, not guarantees, and behavior varies by OpenCV build.
- Mid-stream failure can block read until timeout windows (documented in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)).
- Security hardening is limited by default: RTSP is unencrypted by default, and docs treat trusted LAN as baseline.
- INFERENCE: There is no automated bootstrap script in repo to provision MediaMTX + ffmpeg on Pi, so deployment remains operator-driven.

---

## F3. Network-Based Vision System Design Trade-offs

### Technical evidence summary

Why distributed design was chosen:
- RTSP rollout objective explicitly states physical decoupling of camera and host in [docs/BUILD_LOG.md](../docs/BUILD_LOG.md).
- Evaluation report frames Pi as edge sensor and host as compute node for realistic deployment in [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md).

Measured trade-offs (webcam vs RTSP):
- Reported averages in [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md):
  - camera FPS: 30.0 (webcam) vs 15.0 (RTSP)
  - frame read time: 27.4 ms vs 52.0 ms
  - max pipeline latency: 141.0 ms vs 266.0 ms
  - ML FPS: 10.0 vs 5.0
- Raw DIAG logs align with this in [rtsp_test_log.txt](../rtsp_test_log.txt) and [webcam_test_log.txt](../webcam_test_log.txt).

Latency and buffering implications:
- RTSP integration log states typical LAN end-to-end delay around 0.3-1.5 seconds and explains demux/decode buffering path in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).
- Live stream optimization report shows that removing file I/O alone did not remove lag; decoupled fast/slow threading was required in [reports/live_stream_optimization_report.md](live_stream_optimization_report.md).

Why tight servo tracking is harder:
- Host servo logic includes deadzone/cooldown/opposite-direction lockout specifically to tolerate delayed RTSP feedback in [app/services/servo_service.py](../app/services/servo_service.py) and [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md).

### 1. What existed before

- Local webcam path had no network ingest overhead and no RTSP demux/decode buffering stage.
- Earlier architecture and setup were primarily local-webcam oriented in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) and [docs/SETUP.md](../docs/SETUP.md).

### 2. What changed

- Introduced distributed camera-host split via RTSP source adapter and Pi-side stream assumptions.
- Added diagnostics and comparative evaluations to quantify operational impact.
- Added latency-tolerant servo command policy for distributed loop stability.

### 3. Why it changed

- Practical surveillance deployment needs flexible camera placement and safer host placement, not laptop-tethered optics.
- Project accepted network overhead in exchange for deployment realism and system separation.

### 4. What files matter most

- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/main.py](../app/main.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [rtsp_test_log.txt](../rtsp_test_log.txt)
- [webcam_test_log.txt](../webcam_test_log.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

### 5. Useful snippets

Snippet F3-1 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
Avg Camera FPS: webcam 30.0 fps vs RTSP 15.0 fps
Avg Frame Read Time: webcam 27.4 ms vs RTSP 52.0 ms
Max Pipeline Latency: webcam 141.0 ms vs RTSP 266.0 ms
ML FPS: webcam 10.0 fps vs RTSP 5.0 fps
~~~

Snippet F3-2 from [app/services/servo_service.py](../app/services/servo_service.py)

~~~python
# Global cooldown to avoid issuing commands on stale feedback
if now - self.last_command_time < self.cooldown_period:
    return False

# Block rapid reverse commands (anti-oscillation)
if target_dir != last_dir:
    if not is_extreme:
        return False
~~~

Snippet F3-3 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~text
Typical end-to-end latency over a local LAN: 0.3-1.5 seconds.
To achieve sub-100ms latency, replace cv2.VideoCapture with lower-level pipeline.
RTSP streams are unencrypted by default.
~~~

### 6. How to describe this in report language

- The distributed model is an explicit engineering trade: it sacrifices ingest throughput and control-loop immediacy to gain deployment realism, camera-placement flexibility, and cleaner host-side compute isolation.
- System behavior under network delay is handled by bounded queues, frame decimation, and latency-tolerant control policies rather than by attempting zero-latency guarantees.

### 7. Limitations and honest weaknesses

- Network transport and decode buffering remain first-order latency sources; low-latency flags reduce but do not remove this.
- RTSP over TCP improves reliability but can increase blocking behavior under transient network failure.
- Current deployment story is primarily trusted-LAN; stronger production controls (RTSPS/VPN, command auth) are documented but not implemented in core app.
- Servo control channel is plain HTTP GET without authentication in [app/services/servo_service.py](../app/services/servo_service.py) and [scripts/pi_servo_service.py](../scripts/pi_servo_service.py).
- No automated tests were found for `/live/stream` multi-client load behavior; current dashboard test coverage checks `/live/frame` in [tests/test_dashboard.py](../tests/test_dashboard.py).
- INFERENCE: For high-precision real-time pan/tilt tracking, this architecture is structurally limited by feedback delay and would likely require moving some control logic closer to camera hardware or replacing the capture stack.