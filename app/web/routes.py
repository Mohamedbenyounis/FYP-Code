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
from app.web.auth import login_required, role_required, login_user, logout_user


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
		event.decision_reason = "Matched identity but unauthorised (low confidence)."
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

		login_user(user_id=admin["id"], username=admin["username"], role=admin.get("role", "admin"))
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
	
	period = request.args.get("period", "day")
	now = datetime.now(timezone.utc)
	
	if period == "day":
		local_now = now.astimezone()
		local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
		since_dt = local_midnight.astimezone(timezone.utc)
	elif period == "week":
		since_dt = now - timedelta(days=7)
	elif period == "month":
		since_dt = now - timedelta(days=30)
	elif period == "year":
		since_dt = now - timedelta(days=365)
	else:
		since_dt = None

	if since_dt:
		kpi_events = event_repo.count_events_since(since_dt)
		kpi_auth = event_repo.count_events_since(since_dt, status="authorised")
		kpi_unauth = event_repo.count_events_since(since_dt, status="unauthorised")
		kpi_alerts = alert_repo.count_alerts_since(since_dt)
	else:
		kpi_events = event_repo.count_events()
		kpi_auth = event_repo.count_events(status="authorised")
		kpi_unauth = event_repo.count_events(status="unauthorised")
		kpi_alerts = alert_repo.count_alerts()

	return render_template(
		"dashboard.html",
		period=period,
		total_persons=total_persons,
		total_events=total_events,
		authorised_count=authorised_count,
		unauthorised_count=unauthorised_count,
		recent_events=recent_events,
		recent_alerts=recent_alerts,
		total_alerts=total_alerts,
		kpi_events=kpi_events,
		kpi_auth=kpi_auth,
		kpi_unauth=kpi_unauth,
		kpi_alerts=kpi_alerts,
		recognition_match_threshold=config.RECOGNITION_MATCH_THRESHOLD,
		authorisation_threshold=config.AUTHORISATION_THRESHOLD,
		live_view_enabled=config.LIVE_VIEW_ENABLED,
	)


@web_bp.route("/live/frame")
@login_required
def live_frame():
	"""Serve the latest camera frame for the dashboard near-live view."""
	from multiprocessing import shared_memory
	
	SHM_HEADER = 17  # lock(1) + size(4) + seq(4) + ts(8)
	
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
	
	SHM_HEADER = 17  # lock(1) + size(4) + seq(4) + ts(8)
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
			total_latency = 0.0
			max_latency = 0.0
			
			while True:
				try:
					if shm.buf[0] == 0:
						size = int.from_bytes(shm.buf[1:5], 'little')
						seq = int.from_bytes(shm.buf[5:9], 'little')
						if 0 < size < 2 * 1024 * 1024:
							if seq != last_seq:
								last_seq = seq
								
								import struct
								cap_ts = struct.unpack('<d', shm.buf[9:17])[0]
								latency = (time.monotonic() - cap_ts) * 1000.0
								if latency > 0:
									total_latency += latency
									if latency > max_latency:
										max_latency = latency
									
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
					avg_lat = (total_latency / yield_count) if yield_count > 0 else 0.0
					stream_log.info(
						"[DIAG MJPEG] yield=%.1f fps | stale=%d | err=%d | "
						"lat_avg=%.1fms lat_max=%.1fms | last_seq=%d",
						yfps, stale_count, error_count, avg_lat, max_latency, last_seq,
					)
					diag_t0 = now
					yield_count = 0
					stale_count = 0
					error_count = 0
					total_latency = 0.0
					max_latency = 0.0
				
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
@role_required(["admin"])
def delete_person(person_id: int):
	person_repo, _, _, _ = _repos()
	deleted = person_repo.delete_person(person_id)
	if deleted:
		flash("Person deleted", "success")
	else:
		flash("Person not found", "error")
	return redirect(url_for("web.persons"))


@web_bp.route("/enroll", methods=["GET", "POST"])
@role_required(["admin"])
def enroll():
	if request.method == "POST":
		name = request.form.get("name", "").strip()
		
		# Allow uploading multiple files directly, or camera Blob files
		upload_files = request.files.getlist("images")
		camera_files = request.files.getlist("camera_images")
		
		all_files = upload_files + camera_files
		# Filter out empties that sometimes HTML forms send 
		valid_files = [f for f in all_files if f and f.filename]

		if not name:
			flash("Name is required", "error")
			return render_template("enroll.html"), 400

		if not valid_files:
			flash("At least one image is required", "error")
			return render_template("enroll.html"), 400

		# Decode all images into memory
		from app.services.enrollment_service import decode_uploaded_image, enroll_from_multiple_images
		decoded_images = []
		for f in valid_files:
			img = decode_uploaded_image(f.read())
			if img is not None:
				decoded_images.append(img)
				
		if not decoded_images:
			flash("Failed to decode any provided images.", "error")
			return render_template("enroll.html"), 400

		# Standard upload enforces a more lenient rule if only 1 image uploaded?
		# No, requirements say minimum valid captures recommended: 3.
		# If they upload fewer than 3 manually, we'll gracefully reject, OR we can dynamically threshold it
		# For manual mode, if they only upload 1, maybe they only have 1. Let's cap minimum based on how many they sent.
		# If they send 5 camera shots, require 3. If they upload 1 file, require 1.
		min_caps = 3 if len(decoded_images) >= 3 else len(decoded_images)

		result = enroll_from_multiple_images(name=name, images=decoded_images, min_captures=min_caps)

		if result.success:
			flash(result.message, "success")
			return redirect(url_for("web.persons"))

		flash(result.message, "error")
		return render_template("enroll.html"), 400

	return render_template("enroll.html")


@web_bp.route("/alerts")
@login_required
def alerts():
	_, _, _, alert_repo = _repos()
	items = alert_repo.list_alerts(limit=200, include_acknowledged=True)
	return render_template("alerts.html", alerts=items)


@web_bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
@login_required
def acknowledge_alert(alert_id: int):
	_, _, _, alert_repo = _repos()
	success = alert_repo.acknowledge_alert(alert_id)
	if success:
		if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.accept_json:
			return {"success": True, "message": "Alert acknowledged."}
		flash("Alert acknowledged.", "success")
	else:
		if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.accept_json:
			return {"success": False, "message": "Alert not found."}, 404
		flash("Alert not found.", "error")
	
	# Redirect back for standard form submissions
	next_url = request.referrer or url_for("web.dashboard")
	return redirect(next_url)


@web_bp.route("/settings/users", methods=["GET", "POST"])
@role_required(["admin"])
def user_management():
	_, _, admin_repo, _ = _repos()
	
	if request.method == "POST":
		from werkzeug.security import generate_password_hash
		username = request.form.get("username", "").strip()
		password = request.form.get("password", "")
		role = request.form.get("role", "operator").strip()
		
		val_role = role if role in ["admin", "operator"] else "operator"
		
		if not username or not password:
			flash("Username and password required.", "error")
		elif admin_repo.get_by_username(username):
			flash("User already exists.", "error")
		else:
			pwd_hash = generate_password_hash(password)
			admin_repo.add_user(username=username, password_hash=pwd_hash, role=val_role)
			flash(f"User '{username}' created successfully.", "success")
			return redirect(url_for("web.user_management"))

	users = admin_repo.list_users()
	return render_template("user_management.html", users=users)


@web_bp.route("/delete_user/<int:user_id>", methods=["POST"])
@role_required(["admin"])
def delete_user(user_id: int):
	from flask import session
	_, _, admin_repo, _ = _repos()
	
	if user_id == session.get("user_id"):
		flash("Action Denied: You cannot delete your own account.", "error")
		return redirect(url_for("web.user_management"))
		
	deleted = admin_repo.delete_user(user_id)
	if deleted:
		flash("User deleted.", "success")
	else:
		flash("User not found.", "error")
		
	return redirect(url_for("web.user_management"))
