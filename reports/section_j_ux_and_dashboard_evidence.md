# Section J - UX and Dashboard

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/web/routes.py](../app/web/routes.py)
- [app/web/app_factory.py](../app/web/app_factory.py)
- [app/web/auth.py](../app/web/auth.py)
- [app/web_run.py](../app/web_run.py)
- [app/web/templates/base.html](../app/web/templates/base.html)
- [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)
- [app/web/templates/events.html](../app/web/templates/events.html)
- [app/web/templates/event.html](../app/web/templates/event.html)
- [app/web/templates/alerts.html](../app/web/templates/alerts.html)
- [app/web/templates/persons.html](../app/web/templates/persons.html)
- [app/web/templates/enroll.html](../app/web/templates/enroll.html)
- [app/web/templates/components/_sidebar.html](../app/web/templates/components/_sidebar.html)
- [app/web/templates/components/_event_card.html](../app/web/templates/components/_event_card.html)
- [app/web/templates/components/_alert_row.html](../app/web/templates/components/_alert_row.html)
- [app/web/static/style.css](../app/web/static/style.css)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/db/migrations.py](../app/db/migrations.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_dashboard_temporal.py](../tests/test_dashboard_temporal.py)
- [tests/test_routes.py](../tests/test_routes.py)
- [tests/test_auth.py](../tests/test_auth.py)
- [tests/test_rbac.py](../tests/test_rbac.py)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/SETUP.md](../docs/SETUP.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_webcam_main.txt](../new_webcam_main.txt)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Historical behavior is reconstructed from BUILD/DASHBOARD/ARCHITECTURE logs and evaluation reports.
- Runtime performance statements are taken from preserved DIAG logs where available.
- Any statement not directly explicit in code/docs/logs is marked as INFERENCE.

---

## J1. Flask Dashboard Design & Streaming Interface

### Technical evidence summary

Current dashboard is a server-rendered Flask UI (no SPA framework) with process-level separation:
- Process A (`app.main`) handles camera, ML, eventing, and live frame publication.
- Process B (`app.web_run`) runs Flask routes/templates against SQLite repositories.

Flask web layer shape:
- App creation in [app/web/app_factory.py](../app/web/app_factory.py): registers `web_bp`, opens DB connection via `init_db`, sets session/security config.
- Route/controller layer in [app/web/routes.py](../app/web/routes.py): auth, dashboard KPIs, live endpoints, events, media serving, alerts, persons, enrollment, user management.
- Templates under [app/web/templates/](../app/web/templates/) provide dashboard shell + role-aware navigation + event/alert/person workflows.

Operator UX surface in dashboard:
- Dashboard (`/`) combines live feed panel, KPI cards, recent alerts, and recent event stream.
- Alerts are actionable from the dashboard via AJAX acknowledge.
- Event detail page combines analytics, snapshot, and clip playback in one page.
- Role controls: operators can monitor; admins can enroll/manage users.

### 1. What existed before

Before full UI upgrades:
- Iteration 5 introduced local Flask dashboard MVP with route/template/repo foundations and strict scope guardrails (no clips initially): [docs/BUILD_LOG.md](../docs/BUILD_LOG.md).
- Process split was already intentional (pipeline separate from dashboard process): [docs/SETUP.md](../docs/SETUP.md).
- Early dashboard focused on auth + events/persons/snapshots and safe path handling; this is reflected in foundational tests in [tests/test_dashboard.py](../tests/test_dashboard.py).

### 2. What changed

From MVP to current operator UI:
- Dashboard route (`/`) now computes time-window KPIs (`day/week/month/year/all`) and passes both KPI and recent-stream data to template: [app/web/routes.py](../app/web/routes.py).
- Navigation and page architecture became broader than MVP:
  - `/` dashboard, `/events`, `/events/<id>`, `/alerts`, `/persons`, `/enroll`, `/settings/users`
  - media evidence routes `/events/<id>/snapshot` and `/events/<id>/clip`
  - live feed routes `/live/frame` and `/live/stream`
- Dashboard template integrates live stream directly when `live_view_enabled` is true, then renders alert triage + event stream in same view: [app/web/templates/dashboard.html](../app/web/templates/dashboard.html).
- UX interactions became more operational:
  - AJAX alert acknowledgement in [app/web/templates/base.html](../app/web/templates/base.html)
  - event cards and alert rows via component templates
  - event detail includes both snapshot and in-browser `<video>` evidence playback.
- RBAC expansion (admin vs operator) is now present in templates/routes and covered by tests: [tests/test_rbac.py](../tests/test_rbac.py).

### 3. Why it changed

Why this dashboard architecture exists:
- Project intent shifted from MVP visibility to operational interface (monitor, triage, investigate, administrate) without rewriting backend around SPA/WebSocket complexity.
- SQLite repository abstraction (`app/db/repo.py`) lets routes query counts/lists without embedding SQL in Flask handlers.
- Session auth + role checks provide security boundary for admin functions (`/enroll`, `/settings/users`, delete actions).
- Dashboard event-detail UX was designed to keep investigation in-browser (snapshot + clip + reasoning text) rather than external tooling.

### 4. What files matter most

- [app/web/app_factory.py](../app/web/app_factory.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/web/auth.py](../app/web/auth.py)
- [app/web_run.py](../app/web_run.py)
- [app/web/templates/base.html](../app/web/templates/base.html)
- [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)
- [app/web/templates/event.html](../app/web/templates/event.html)
- [app/web/templates/components/_sidebar.html](../app/web/templates/components/_sidebar.html)
- [app/db/repo.py](../app/db/repo.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_dashboard_temporal.py](../tests/test_dashboard_temporal.py)
- [tests/test_rbac.py](../tests/test_rbac.py)

### 5. Useful snippets

Snippet J1-1 from [app/web/routes.py](../app/web/routes.py)

```python
@web_bp.route("/")
@login_required
def dashboard():
    ...
    period = request.args.get("period", "day")
    ...
    return render_template(
        "dashboard.html",
        period=period,
        ...
        recent_events=recent_events,
        recent_alerts=recent_alerts,
        ...
        live_view_enabled=config.LIVE_VIEW_ENABLED,
    )
```

Snippet J1-2 from [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)

```html
{% if live_view_enabled %}
<section>
  <h3>Live Feed ...</h3>
  <div class="video-container">
    <img src="{{ url_for('web.live_stream') }}" alt="Live camera feed">
  </div>
</section>
{% endif %}

<h3 style="color: var(--status-danger);">Priority Alerts</h3>
...
<h3>Live Event Stream</h3>
```

Snippet J1-3 from [app/web/templates/base.html](../app/web/templates/base.html)

```javascript
document.addEventListener('submit', function(e) {
  if (e.target && e.target.classList.contains('ajax-acknowledge-form')) {
    e.preventDefault();
    fetch(form.action, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json'
      }
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) { ... alertRow.remove() ... }
    });
  }
});
```

### 6. How to describe this in report language

- The dashboard is implemented as a modular Flask presentation layer that sits beside (not inside) the real-time vision pipeline. This separation preserves runtime safety while providing operators with a single operational surface for live monitoring, incident triage, evidence playback, and administrative control.
- UX is task-oriented rather than visual-only: the main page couples live camera context with active alerts and recent detections, while event detail consolidates decision explanation plus snapshot/clip media for faster incident review.

### 7. Limitations / honest weaknesses

- Live stream route (`/live/stream`) does not currently have dedicated automated tests; dashboard tests primarily verify `/live/frame` behavior and route security in [tests/test_dashboard.py](../tests/test_dashboard.py).
- Event/alert lists are server-rendered and bounded (for example `limit=200` on listing routes), with no infinite-scroll/pagination UX.
- UI is Flask-template based with imperative JS helpers; there is no richer client-state model for advanced triage workflows.
- INFERENCE: Multi-client scale behavior for MJPEG endpoint is not benchmarked in the repository tests/docs.

---

## J2. Live Preview vs Live Stream Trade-off

### Technical evidence summary

The repository shows an evolution from simple near-live frame polling to shared-memory MJPEG streaming, driven by latency and blocking problems.

Current mechanism (code truth):
- Producer in [app/main.py](../app/main.py) encodes JPEG frames and publishes to shared memory `sv_live_frame` with metadata header (`lock/size/seq/timestamp`).
- Consumer in [app/web/routes.py](../app/web/routes.py):
  - `/live/frame` one-shot JPEG response from shared memory
  - `/live/stream` multipart MJPEG generator from shared memory with sequence-based staleness control and DIAG logging.
- Dashboard now embeds `/live/stream` directly via `<img>`.

### 1. What existed before

Historical dashboard live-view path (docs/report evidence):
- Iteration 12 docs describe writing `data/latest_frame.jpg` in pipeline and polling `/live/frame` with cache-busting JS every ~800ms: [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md), [docs/BUILD_LOG.md](../docs/BUILD_LOG.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
- Early optimization report documents the original disk handoff between `app.main` and Flask (`latest_frame.jpg`) and observed severe lag (~1 FPS) despite faster native OpenCV preview: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md).

### 2. What changed

Streaming stack changed in two stages:

1) Disk handoff to shared memory transport
- `latest_frame.jpg` file handoff was replaced by `multiprocessing.shared_memory` block `sv_live_frame` to remove file-lock contention and reduce handoff overhead.

2) Runtime architecture refactor to producer-consumer threading
- Fast loop captures and publishes frequently; slow loop handles ML/event/clip/alerts using bounded queue (`maxsize=1`) to drop stale frames.
- Flask `live_stream` yields only when sequence number changes, preventing duplicate stale sends.

Current evidence of delivered behavior:
- RTSP run MJPEG diagnostics in [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt) show yields around 6.6-7.8 fps with non-zero stale counts and zero route errors.
- Webcam run fast-loop diagnostics in [new_webcam_main.txt](../new_webcam_main.txt) show higher capture/publish rates (cam around high-20 fps, enc around mid-teens fps), indicating better responsiveness for local camera mode.

### 3. Why it changed

The design changed because earlier approach hit real bottlenecks:
- Disk polling path created locking/crash pressure and did not solve lag by itself.
- Root cause was synchronous main-loop starvation under combined ML + DB + clip + alert work.
- System adopted decoupled fast/slow loops and stale-frame dropping to prioritize freshness and stability.

Priority outcome implied by code/config/logs:
- Prioritized: responsiveness and pipeline correctness under load.
- De-prioritized: perfect frame completeness and maximum visual fidelity.
  - Evidence: `PROCESS_EVERY_N_FRAMES`, `LIVE_VIEW_EVERY_N_FRAMES`, `queue.Queue(maxsize=1)`, JPEG quality 65.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)
- [app/config.py](../app/config.py)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_webcam_main.txt](../new_webcam_main.txt)

### 5. Useful snippets

Snippet J2-1 from [app/main.py](../app/main.py)

```python
frame_queue: queue.Queue = queue.Queue(maxsize=1)
...
if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
    try:
        frame_queue.put_nowait(frame.copy())
    except queue.Full:
        fast_diag.tick_queue_drop()
...
if frame_counter % config.LIVE_VIEW_EVERY_N_FRAMES == 0:
    success, buffer = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
```

Snippet J2-2 from [app/web/routes.py](../app/web/routes.py)

```python
if seq != last_seq:
    last_seq = seq
    frame_data = bytes(shm.buf[SHM_HEADER:SHM_HEADER+size])
    yield (b'--frame\r\n'
           b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
else:
    stale_count += 1
...
stream_log.info("[DIAG MJPEG] yield=%.1f fps | stale=%d | err=%d | ...")
```

Snippet J2-3 from [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

```text
[DIAG MJPEG] yield=7.8 fps | stale=85 | err=0 | lat_avg=86.6ms lat_max=156.0ms
[DIAG MJPEG] yield=6.6 fps | stale=73 | err=0 | lat_avg=88.5ms lat_max=156.0ms
[DIAG MJPEG] yield=7.0 fps | stale=80 | err=0 | lat_avg=95.0ms lat_max=453.0ms
```

### 6. How to describe this in report language

- The project evolved from a lightweight near-live polling approach to a shared-memory MJPEG streaming pipeline after empirical latency debugging. Transport optimization alone was insufficient; the decisive improvement came from architectural decoupling (fast producer vs slow ML consumer) and explicit stale-frame dropping.
- Final UX trade-off: the dashboard favors temporal freshness and operational stability over full-frame continuity and highest-quality rendering. This is suitable for surveillance monitoring where current situational awareness is more critical than preserving every intermediate frame.

### 7. Limitations / honest weaknesses

- Documentation drift exists:
  - Some docs still describe `latest_frame.jpg` polling, while current code uses shared memory and `/live/stream`.
- End-user glass-to-glass latency is not fully benchmarked in a dedicated automated suite; [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) explicitly separates core-engine metrics from dashboard-perceived delay.
- Shared memory buffer is fixed at 2MB (`SHM_TOTAL_SIZE`); oversized frames are skipped.
- MJPEG is bandwidth-heavy relative to inter-frame codecs and can be less efficient at scale.
- No explicit repository evidence of load tests for many concurrent dashboard clients on `/live/stream`.
- INFERENCE: Under high client concurrency, Flask dev-server style streaming may require production WSGI/ASGI hardening for predictable latency.
