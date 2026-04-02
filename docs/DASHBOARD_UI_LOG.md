# Dashboard UI Design Log (Iteration 12)

## Architectural Constraints

When upgrading the dashboard, a hard constraint was preserving the `main.py` vs `web_run.py` process split. The core inference loops (via `WebcamCamera` and `FacePipeline`) run continuously inside `main.py`, while `web_run.py` mounts the synchronous Flask application. 

Attempting to mount true low-latency real-time streams (like RTSP or HTTP MJPEG multi-part streams) directly from Flask would either require running OpenCV capture inside the Web Server (destroying the modular data pipeline schema we've spent 11 iterations securing) or building complex Redis/IPC messaging buses between the two discrete python processes.

## Solutions Chosen

### Near-Live Javascript Polling
To provide operators with immediate visual confirmation of the camera feed, we injected a highly decoupled export hook inside `app/main.py`.

```python
if config.LIVE_VIEW_ENABLED and frame_counter % config.LIVE_VIEW_EVERY_N_FRAMES == 0:
    cv2.imwrite(str(config.DATA_DIR / "latest_frame.jpg"), display_frame)
```

The Flask web app exposes `/live/frame` which serves this file with strictly enforced `Cache-Control: no-cache` headers. Finally, a lightweight 800ms `setInterval` Javascript loop built into the new dashboard automatically requests that file over and over using URL timestamp query injections (e.g. `?t=1295982823759`) to bypass the browser's disk cache.

This provides an effectively "hands-off" 1.5 FPS live stream to exactly one or more parallel dashboard clients without the main inference loop ever blocking or locking.

### HTML5 Video Embed Support
To display the video clips (recorded since Iteration 10) directly inside the browser, the config defaults were updated to use `avc1` — the official FourCC tag for H.264 video. Browsers inherently reject generic MPEG-4 streams (the standard `mp4v` OpenCV fallback hook) as security vulnerabilities. 

A new isolated route (`/events/<event_id>/clip`) handles path unpacking securely inside `CLIPS_DIR` and passes the resulting bitstream directly into native `<video controls>` blocks in `event.html`, meaning operators never have to download evidence zips or run secondary software to investigate breaches.
