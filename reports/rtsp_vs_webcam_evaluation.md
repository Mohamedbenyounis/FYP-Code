# Evaluation Report: RTSP vs Local Webcam Integration

## 1. Introduction

The SecureVision system was originally designed with local webcam support via USB/built-in cameras. However, a local-only camera limits the system's physical deployment flexibility in real-world scenarios. To solve this, we integrated an RTSP (Real-Time Streaming Protocol) ingestion layer, allowing SecureVision to process frames captured by an external Raspberry Pi Camera Module over a local area network (LAN).

Comparing the two input modes is critical. While a network stream offers physical decoupling (the host machine can be tucked away securely while the Pi acts as the edge sensor), it introduces additional overhead and can reduce effective throughput due to decoding and network transport costs. This evaluation measures and empirically analyses the performance trade-offs—specifically focusing on frame throughput and process-blocking latency—between the local webcam and the remote RTSP stream.

---

## 2. Methodology

To conduct an objective comparison, lightweight thread-safe instrumentation was integrated into the SecureVision system. Measurements were captured across the application's core pipeline using isolated execution logs:
- **Fast Thread (`[DIAG FAST]`)**: Calculates raw camera read frames-per-second (FPS), average read-blocking time per frame (ms), encoded JPEG size, and internal queue drop rates.
- **Slow Thread (`[DIAG SLOW]`)**: Measures the ML face detection pipeline throughput.

**Hardware & Configuration Check:**
- **Host**: Local machine running the SecureVision backend.
- **RTSP Source**: Raspberry Pi Camera Module v3, running `mediamtx` with `rpicam-vid`.
- **Stream Format**: H.264 over TCP.
- **Resolution**: Both modes strictly enforced to 640x480 to isolate transport latency from resolution scaling overhead.
- **Duration**: Each test run was maintained under stable lighting for 60 seconds. `PROCESS_EVERY_N_FRAMES` was set to `3` in `app/config.py`.

*Note: Stream (MJPEG) FPS and end-to-end user latency were excluded from this dataset as they are handled by the asynchronous dashboard web process (`app.web_run`), isolating our metrics specifically to the core engine's ingestion capabilities.*

---

## 3. Results Table

The metrics collected across the 60-second empirical runs are presented below. 

| Metric | Local Webcam (640x480) | RTSP Network Stream (640x480) |
|---|---|---|
| **Avg Camera FPS** | 30.0 fps | 15.0 fps |
| **Stream FPS (MJPEG)** | 14.8 fps | 7.5 fps |
| **Avg Frame Read Time** | 27.4 ms | 52.0 ms |
| **Avg Pipeline Latency** | 53.4 ms | 59.1 ms |
| **Max Pipeline Latency** | 141.0 ms | 266.0 ms |
| **Internal Frame Drops** | < 0.1% | < 0.1% |
| **ML FPS** | 10.0 fps | 5.0 fps |

*(Note: Streaming performance is naturally halved by `LIVE_VIEW_EVERY_N_FRAMES=2`. ML throughput is locked to 1/3 of ingestion via `PROCESS_EVERY_N_FRAMES=3`).*

---

## 4. Analysis

### Ingestion Overhead & Read Blocking
The `cv2.VideoCapture.read()` cycle is the primary bottleneck for the "Fast Thread". For local webcams, the blocking time is **27.4 ms**, allowing for a stable 30 FPS ceiling with CPU cycles to spare. For RTSP, this increases to **52.0 ms**. This doubling of read time is the "ingestion cost"—the time taken for OpenCV to demux the TCP packets and for the CPU to decode the H.264 I/P-frames into raw BGR arrays.

### Internal Pipeline Latency vs. Observed Delay
A critical distinction must be made between **Pipeline Latency** and **Network Ingestion Delay**.
- **Avg Pipeline Latency (59.1 ms)**: This measures the time from the frame entering the host memory to it being yielded to the dashboard. Both webcam and RTSP perform similarly here, proving the backend threads are efficient.
- **Network Ingestion Delay (Observed ~0.5s - 1.5s)**: This is the time the frame spends "in flight"—encoding on the Pi, traveling over Wi-Fi, and sitting in the FFmpeg demuxer buffer. This is not captured by host-side timestamps but is responsible for the visual lag observed by the user.

### Pipeline Throughput & Stability
Both pipelines demonstrated near-zero frame drops within the system queues. This confirms that the 1/3 ML processing split is a sustainable architecture for both local and remote edge-node deployments. The RTSP stream provides a wider deployment field-of-view depending on camera configuration, which can be advantageous for security monitoring compared to fixed laptop webcams.

---

## 5. Limitations

1. **Host-Bound Decode Limitation**: The raw Python/OpenCV approach utilizes CPU-based decoding for the incoming H.264 network stream. A host-layer hardware-accelerated decode pipeline would reduce the observed read latency.
2. **Dashboard Disconnect**: Because the MJPEG streaming endpoint was structurally decoupled into a secondary Flask process, the visual glass-to-glass latency experienced by the end-user on the web dashboard was not measured in this core engine benchmark.
3. **LAN Viability Only**: The test achieved a near-zero drop rate over a Local Area Network. Introducing a WAN or external cellular connection would likely increase packet loss and inflate peak read times.

---

## 6. Conclusion 

The integration of the RTSP stream was successful at decoupling the camera from the host machine while maintaining system stability (near-zero dropped frames).

Webcam mode remains the superior choice for prototype development and responsive local testing, offering ~30 FPS ingestion with ~30 ms read latency. However, RTSP is justified for realistic deployment scenarios where the processing system must be physically separated from the camera.

While the measured pipeline latency is ~59 ms, the **true end-to-end perceived latency is significantly higher (~0.5–1.5 seconds)** due to network transport and decoding buffers. This overhead is acceptable for a smart surveillance system, where deployment flexibility outweighs strict real-time responsiveness.