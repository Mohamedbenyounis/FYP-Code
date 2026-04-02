"""
Flask routes for web dashboard.
Iteration 5 dashboard implementation.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone

from flask import (
	Blueprint,
	abort,
	current_app,
	flash,
	redirect,
	render_template,
	request,
	send_file,
	url_for,
	make_response,
)
from werkzeug.security import check_password_hash

from app import config
from app.db.repo import (
	AdminRepository,
	SQLiteEventRepository,
	SQLitePersonRepository,
	SQLiteAlertRepository,
)
from app.services.enrollment_service import decode_uploaded_image, enroll_from_image
from app.web.auth import login_required, login_user, logout_user


web_bp = Blueprint("web", __name__)


def _repos() -> tuple[SQLitePersonRepository, SQLiteEventRepository, AdminRepository, SQLiteAlertRepository]:
	conn = current_app.config["DB_CONN"]
	return (
		SQLitePersonRepository(conn),
		SQLiteEventRepository(conn),
		AdminRepository(conn),
		SQLiteAlertRepository(conn),
	)


def _resolve_snapshot_db_path(snapshot_path: str) -> Path | None:
	"""Resolve DB snapshot path only if it stays inside snapshots directory."""
	if not snapshot_path:
		return None

	rel = Path(snapshot_path.replace("\\", "/"))
	if rel.is_absolute():
		return None

	absolute = (config.BASE_DIR / rel).resolve()
	snapshots_root = Path(current_app.config["SNAPSHOTS_DIR"]).resolve()

	try:
		if not absolute.is_relative_to(snapshots_root):
			return None
	except AttributeError:
		try:
			absolute.relative_to(snapshots_root)
		except ValueError:
			return None

	return absolute if absolute.exists() else None


def _resolve_clip_db_path(clip_path: str) -> Path | None:
	"""Resolve DB clip path safely inside the clips directory."""
	if not clip_path:
		return None

	rel = Path(clip_path.replace("\\", "/"))
	if rel.is_absolute():
		return None

	absolute = (config.BASE_DIR / rel).resolve()
	
	try:
		clips_dir = current_app.config.get("CLIPS_DIR")
	except KeyError:
		clips_dir = config.CLIPS_DIR
		
	if clips_dir is None:
		clips_dir = config.CLIPS_DIR
		
	clips_root = Path(clips_dir).resolve()

	try:
		if not absolute.is_relative_to(clips_root):
			return None
	except AttributeError:
		try:
			absolute.relative_to(clips_root)
		except ValueError:
			return None

	return absolute if absolute.exists() else None


def _decorate_event_for_display(event) -> None:
	"""Attach presentation-only event display fields (no DB/schema changes)."""
	if event.person_name and event.status == "authorised":
		event.display_state = "authorised_match"
		event.decision_reason = (
			"Matched identity and met authorisation threshold "
			f"(>= {config.AUTHORISATION_THRESHOLD:.3f})."
		)
	elif event.person_name and event.status == "unauthorised":
		event.display_state = "low_confidence_match"
		event.decision_reason = (
			"Matched identity but below authorisation threshold "
			f"(< {config.AUTHORISATION_THRESHOLD:.3f})."
		)
	else:
		event.display_state = "unknown"
		event.decision_reason = (
			"No identity match above recognition threshold "
			f"(>= {config.RECOGNITION_MATCH_THRESHOLD:.3f})."
		)


@web_bp.route("/login", methods=["GET", "POST"])
def login():
	if request.method == "POST":
		username = request.form.get("username", "").strip()
		password = request.form.get("password", "")
		_, _, admin_repo, _ = _repos()

		admin = admin_repo.get_by_username(username)
		if admin is None or not check_password_hash(admin["password_hash"], password):
			flash("Invalid username or password", "error")
			return render_template("login.html"), 401

		login_user(admin_id=admin["id"], username=admin["username"])
		return redirect(url_for("web.dashboard"))

	return render_template("login.html")


@web_bp.route("/logout")
def logout():
	logout_user()
	return redirect(url_for("web.login"))


@web_bp.route("/")
@login_required
def dashboard():
	person_repo, event_repo, _, alert_repo = _repos()
	total_persons = person_repo.count_persons()
	total_events = event_repo.count_events()
	authorised_count = event_repo.count_events(status="authorised")
	unauthorised_count = event_repo.count_events(status="unauthorised")
	recent_events = event_repo.list_events(limit=10)
	for event in recent_events:
		_decorate_event_for_display(event)

	recent_alerts = alert_repo.list_alerts(limit=5)
	total_alerts = alert_repo.count_alerts()
	
	# Compute 24-hour analytics
	yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
	events_24h = event_repo.count_events_since(yesterday)
	auth_24h = event_repo.count_events_since(yesterday, status="authorised")
	unauth_24h = event_repo.count_events_since(yesterday, status="unauthorised")
	alerts_24h = alert_repo.count_alerts_since(yesterday)

	return render_template(
		"dashboard.html",
		total_persons=total_persons,
		total_events=total_events,
		authorised_count=authorised_count,
		unauthorised_count=unauthorised_count,
		recent_events=recent_events,
		recent_alerts=recent_alerts,
		total_alerts=total_alerts,
		events_24h=events_24h,
		auth_24h=auth_24h,
		unauth_24h=unauth_24h,
		alerts_24h=alerts_24h,
		recognition_match_threshold=config.RECOGNITION_MATCH_THRESHOLD,
		authorisation_threshold=config.AUTHORISATION_THRESHOLD,
		live_view_enabled=config.LIVE_VIEW_ENABLED,
	)


@web_bp.route("/live/frame")
@login_required
def live_frame():
	"""Serve the latest camera frame for the dashboard near-live view."""
	from multiprocessing import shared_memory
	
	SHM_HEADER = 9  # lock(1) + size(4) + seq(4)
	
	try:
		shm = shared_memory.SharedMemory(name="sv_live_frame")
	except FileNotFoundError:
		abort(503, "Camera pipeline not running")

	try:
		if shm.buf[0] == 1:
			import time
			time.sleep(0.01)

		if shm.buf[0] == 0:
			size = int.from_bytes(shm.buf[1:5], 'little')
			if 0 < size < 2 * 1024 * 1024:
				frame_data = bytes(shm.buf[SHM_HEADER:SHM_HEADER+size])
				response = make_response(frame_data)
				response.headers.set('Content-Type', 'image/jpeg')
				response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
				response.headers['Pragma'] = 'no-cache'
				return response
	finally:
		shm.close()

	abort(503, "Frame not available")


@web_bp.route("/live/stream")
@login_required
def live_stream():
	"""Streams the latest camera frame natively via Shared Memory MJPEG."""
	import time
	import logging
	from flask import Response
	from multiprocessing import shared_memory
	
	SHM_HEADER = 9  # lock(1) + size(4) + seq(4)
	DIAG_INTERVAL = 5.0
	stream_log = logging.getLogger("securevision.mjpeg")
	
	def generate():
		shm = None
		while shm is None:
			try:
				shm = shared_memory.SharedMemory(name="sv_live_frame")
			except FileNotFoundError:
				time.sleep(0.5)
		
		try:
			last_seq = 0
			# Diagnostics
			diag_t0 = time.monotonic()
			yield_count = 0
			stale_count = 0
			error_count = 0
			last_fresh_t = time.monotonic()
			
			while True:
				try:
					if shm.buf[0] == 0:
						size = int.from_bytes(shm.buf[1:5], 'little')
						seq = int.from_bytes(shm.buf[5:9], 'little')
						if 0 < size < 2 * 1024 * 1024:
							if seq != last_seq:
								last_seq = seq
								frame_data = bytes(shm.buf[SHM_HEADER:SHM_HEADER+size])
								yield (b'--frame\r\n'
									   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
								yield_count += 1
								last_fresh_t = time.monotonic()
							else:
								stale_count += 1
				except Exception:
					error_count += 1
				
				# Periodic diagnostics
				now = time.monotonic()
				if now - diag_t0 >= DIAG_INTERVAL:
					elapsed = now - diag_t0
					yfps = yield_count / elapsed if elapsed > 0 else 0
					stale_sec = now - last_fresh_t
					stream_log.info(
						"[DIAG MJPEG] yield=%.1f fps | stale=%d | err=%d | "
						"last_fresh=%.1fs ago | last_seq=%d",
						yfps, stale_count, error_count, stale_sec, last_seq,
					)
					diag_t0 = now
					yield_count = 0
					stale_count = 0
					error_count = 0
				
				time.sleep(0.04)
		finally:
			shm.close()

	return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@web_bp.route("/events")
@login_required
def events():
	_, event_repo, _, _ = _repos()
	status_filter = request.args.get("status")
	if status_filter in {"authorised", "unauthorised"}:
		items = event_repo.list_events(limit=200, status=status_filter)
	else:
		items = event_repo.list_events(limit=200)
	for event in items:
		_decorate_event_for_display(event)
	return render_template(
		"events.html",
		events=items,
		status_filter=status_filter,
		recognition_match_threshold=config.RECOGNITION_MATCH_THRESHOLD,
		authorisation_threshold=config.AUTHORISATION_THRESHOLD,
	)


@web_bp.route("/events/<event_id>")
@login_required
def event_detail(event_id: str):
	_, event_repo, _, _ = _repos()
	event = event_repo.get_event_by_id(event_id)
	if event is None:
		abort(404)
	_decorate_event_for_display(event)
	snapshot_available = _resolve_snapshot_db_path(event.snapshot_path or "") is not None
	clip_available = _resolve_clip_db_path(event.clip_path or "") is not None
	
	return render_template(
		"event.html",
		event=event,
		snapshot_available=snapshot_available,
		clip_available=clip_available,
		recognition_match_threshold=config.RECOGNITION_MATCH_THRESHOLD,
		authorisation_threshold=config.AUTHORISATION_THRESHOLD,
	)


@web_bp.route("/events/<event_id>/snapshot")
@login_required
def event_snapshot(event_id: str):
	_, event_repo, _, _ = _repos()
	event = event_repo.get_event_by_id(event_id)
	if event is None or not event.snapshot_path:
		abort(404)

	resolved = _resolve_snapshot_db_path(event.snapshot_path)
	if resolved is None:
		abort(404)

	return send_file(resolved)


@web_bp.route("/events/<event_id>/clip")
@login_required
def event_clip(event_id: str):
	"""Serve video clips via event ID, constrained to the clips directory."""
	_, event_repo, _, _ = _repos()
	event = event_repo.get_event_by_id(event_id)
	if event is None or not event.clip_path:
		abort(404)

	resolved = _resolve_clip_db_path(event.clip_path)
	if resolved is None:
		abort(404)

	# Using standard mp4 mimetype ensures HTML5 `<video>` treats it correctly.
	return send_file(resolved, mimetype='video/mp4')


@web_bp.route("/persons")
@login_required
def persons():
	person_repo, _, _, _ = _repos()
	summaries = person_repo.list_person_summaries()
	return render_template("persons.html", persons=summaries)


@web_bp.route("/persons/<int:person_id>/delete", methods=["POST"])
@login_required
def delete_person(person_id: int):
	person_repo, _, _, _ = _repos()
	deleted = person_repo.delete_person(person_id)
	if deleted:
		flash("Person deleted", "success")
	else:
		flash("Person not found", "error")
	return redirect(url_for("web.persons"))


@web_bp.route("/enroll", methods=["GET", "POST"])
@login_required
def enroll():
	if request.method == "POST":
		name = request.form.get("name", "").strip()
		file = request.files.get("image")

		if not name:
			flash("Name is required", "error")
			return render_template("enroll.html"), 400

		if file is None or not file.filename:
			flash("Image is required", "error")
			return render_template("enroll.html"), 400

		image = decode_uploaded_image(file.read())
		result = enroll_from_image(name=name, image=image)

		if result.success:
			flash(f"Enrollment successful for {name}", "success")
			return redirect(url_for("web.persons"))

		flash(result.message, "error")
		return render_template("enroll.html"), 400

	return render_template("enroll.html")


@web_bp.route("/alerts")
@login_required
def alerts():
	_, _, _, alert_repo = _repos()
	items = alert_repo.list_alerts(limit=200)
	return render_template("alerts.html", alerts=items)
