# RTSP Camera Integration — Setup & Notes

> **Iteration**: Bonus deployment iteration  
> **Date**: 2026-04-04  
> **Scope**: RTSP stream ingestion from Raspberry Pi Camera Module v3

---

## Overview

SecureVision can now ingest frames from a remote RTSP camera stream instead of
(or in addition to) the local webcam.  This enables the primary deployment
scenario: a Raspberry Pi with a Camera Module streams video over the local
network, and SecureVision processes frames on a more powerful host machine.

---

## 1. Pi-Side Stream Setup

SecureVision does **not** include an RTSP server.  The Raspberry Pi must run
its own RTSP endpoint.  Below are two recommended approaches.

### Option A — MediaMTX (recommended)

[MediaMTX](https://github.com/bluenviern/mediamtx) (formerly rtsp-simple-server)
is a lightweight, zero-config RTSP/RTMP/HLS server.

```bash
# Install on the Pi
wget https://github.com/bluenviern/mediamtx/releases/latest/download/mediamtx_v1.x.x_linux_arm64v8.tar.gz
tar xzf mediamtx_*.tar.gz
chmod +x mediamtx

# Start the server (default port 8554)
./mediamtx &

# Stream the Pi camera into MediaMTX
rpicam-vid -t 0 --width 640 --height 480 --framerate 15 --codec h264 \
  --inline -o - | ffmpeg -i - -c copy -f rtsp rtsp://localhost:8554/cam
```

The resulting stream URL (from your host machine) will be:

```
rtsp://<PI_IP>:8554/cam
```

### Option B — v4l2rtspserver

A minimal alternative that exposes the V4L2 device directly as RTSP.

```bash
sudo apt install v4l2rtspserver
v4l2rtspserver -W 640 -H 480 -F 15 /dev/video0
```

Default stream URL:

```
rtsp://<PI_IP>:8554/unicast
```

### Recommended Stream Settings

| Parameter   | Recommended Value | Notes                                       |
|-------------|-------------------|---------------------------------------------|
| Resolution  | 640×480           | Sufficient for face detection; lower latency |
| Frame Rate  | 15 fps            | Matches SecureVision's processing cadence    |
| Codec       | H.264             | Universal OpenCV/FFmpeg support              |
| Transport   | TCP                | More reliable than UDP over Wi-Fi            |

Higher resolutions (720p, 1080p) work but increase latency and network load.
Only increase if detection accuracy at distance is insufficient.

---

## 2. SecureVision Configuration

Set these environment variables **before** starting SecureVision:

```bash
# Switch camera source from webcam to RTSP
export SV_CAMERA_TYPE=rtsp

# Specify the full RTSP URL from Step 1
export SV_RTSP_URL=rtsp://192.168.1.50:8554/cam
```

Or on Windows (PowerShell):

```powershell
$env:SV_CAMERA_TYPE = "rtsp"
$env:SV_RTSP_URL = "rtsp://192.168.1.50:8554/cam"
```

Then start the application normally:

```bash
python -m app.main
```

### Config Reference

| Variable          | Default   | Description                                    |
|-------------------|-----------|------------------------------------------------|
| `SV_CAMERA_TYPE`  | `webcam`  | Camera source: `webcam` or `rtsp`              |
| `SV_CAMERA_INDEX` | `0`       | Webcam device index (only used when `webcam`)  |
| `SV_RTSP_URL`     | *(empty)* | Full RTSP URL (required when `rtsp`)           |

---

## 3. How It Works Internally

```
┌──────────────────────┐     RTSP/TCP     ┌──────────────────────────┐
│  Raspberry Pi        │ ───────────────► │  SecureVision Host       │
│  Camera Module v3    │                  │                          │
│  + MediaMTX (RTSP)   │                  │  RTSPCamera              │
│                      │                  │    └─ cv2.VideoCapture   │
│  rpicam-vid → ffmpeg │                  │    └─ read() / reconnect │
└──────────────────────┘                  │                          │
                                          │  main.py fast loop       │
                                          │    └─ same as webcam     │
                                          └──────────────────────────┘
```

1. `main.py` reads `SV_CAMERA_TYPE` and creates either `WebcamCamera` or
   `RTSPCamera`.
2. `RTSPCamera` opens the stream via `cv2.VideoCapture(url, CAP_FFMPEG)`.
3. The fast loop calls `camera.read()` identically for both camera types.
4. If `read()` fails, `main.py` calls `camera.reconnect()` which retries up
   to 5 times with 2-second pauses.
5. The ML pipeline, event manager, alerts, and dashboard are completely
   unaware of the camera source — they receive frames the same way.

---

## 4. Known Limitations

### Latency

OpenCV uses FFmpeg to decode RTSP streams.  The decode pipeline
(demuxer → decoder → frame buffer) introduces **0.3–1.5 seconds** of
end-to-end latency on a typical LAN.

We apply several best-effort mitigations:
- `CAP_PROP_BUFFERSIZE = 1` (reduces OpenCV's internal frame queue)
- FFmpeg options: `fflags=nobuffer`, `flags=low_delay`, `framedrop=1`

**However**: These are hints, not guarantees.  `CAP_PROP_BUFFERSIZE` is only
supported by certain OpenCV+FFmpeg build combinations.  If the backend
ignores it, the setting is silently skipped.

**To achieve sub-100ms latency**, you would need to replace `cv2.VideoCapture`
with a raw GStreamer pipeline or a direct V4L2-over-network solution.  This
is out of scope for the current iteration.

### Network Dependency

- Wi-Fi congestion can cause frame drops and stalls.
- If the Pi reboots or the stream process crashes, `RTSPCamera` will attempt
  reconnection (up to 5 retries).  If all fail, SecureVision exits cleanly.
- Use a **wired Ethernet** connection between Pi and host for best reliability.

### Blocking Read

When an RTSP stream dies mid-connection, `cv2.VideoCapture.read()` may block
for several seconds (TCP timeout) before returning `False`.  During this time,
the fast loop in `main.py` is paused.  The ML slow thread continues processing
any queued frame but will not receive new ones until the fast loop recovers.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Failed to open RTSP stream` | Wrong URL, Pi not streaming, firewall | Verify URL with `ffplay rtsp://...`; check Pi service is running |
| `Frame read failed` (repeated) | Stream dropped, network issue | Check Wi-Fi signal; use Ethernet; verify Pi process |
| High latency (>2s) | Large resolution, congested network | Reduce to 640×480@15fps; use wired connection |
| `CAP_PROP_BUFFERSIZE → accepted=False` | OpenCV backend doesn't support it | Informational only — no action needed; camera still works |
| Black frames | Codec mismatch | Ensure Pi streams H.264; check `rpicam-vid --codec h264` |

### Quick Verification

Test the Pi stream independently before connecting SecureVision:

```bash
# On the host machine, verify the stream with ffplay
ffplay rtsp://192.168.1.50:8554/cam

# Or with VLC
vlc rtsp://192.168.1.50:8554/cam
```

If `ffplay` shows video, SecureVision will too.

---

## 6. Security Considerations

- RTSP streams are **unencrypted by default**.  On a trusted home/lab LAN,
  this is acceptable.
- For production deployments, consider RTSP-over-TLS (RTSPS) or VPN tunnels.
- If authentication is required, embed credentials in the URL:
  `rtsp://user:password@host:port/path`

---

## 7. Future Improvements (Out of Scope)

These are explicitly **not** implemented in this iteration:

- Multi-camera support (multiple RTSP streams simultaneously)
- ONVIF device discovery
- GStreamer-based capture for true low-latency
- Pi-side recording or local processing
- Cloud relay / remote access
