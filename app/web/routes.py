"""
Flask routes for web dashboard.
Iteration 5 dashboard implementation.
"""

from __future__ import annotations

from pathlib import Path

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
)
from werkzeug.security import check_password_hash

from app import config
from app.db.repo import (
	AdminRepository,
	SQLiteEventRepository,
	SQLitePersonRepository,
)
from app.services.enrollment_service import decode_uploaded_image, enroll_from_image
from app.web.auth import login_required, login_user, logout_user


web_bp = Blueprint("web", __name__)


def _repos() -> tuple[SQLitePersonRepository, SQLiteEventRepository, AdminRepository]:
	conn = current_app.config["DB_CONN"]
	return (
		SQLitePersonRepository(conn),
		SQLiteEventRepository(conn),
		AdminRepository(conn),
	)


def _resolve_snapshot_db_path(snapshot_path: str) -> Path | None:
	"""Resolve DB snapshot path only if it stays inside snapshots directory."""
	if not snapshot_path:
		return None

	# Normalise separators so Windows-style DB paths resolve reliably.
	rel = Path(snapshot_path.replace("\\", "/"))
	if rel.is_absolute():
		return None

	absolute = (config.BASE_DIR / rel).resolve()
	snapshots_root = Path(current_app.config["SNAPSHOTS_DIR"]).resolve()

	try:
		if not absolute.is_relative_to(snapshots_root):
			return None
	except AttributeError:
		# Python <3.9 fallback
		try:
			absolute.relative_to(snapshots_root)
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
		_, _, admin_repo = _repos()

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
	person_repo, event_repo, _ = _repos()
	total_persons = person_repo.count_persons()
	total_events = event_repo.count_events()
	authorised_count = event_repo.count_events(status="authorised")
	unauthorised_count = event_repo.count_events(status="unauthorised")
	recent_events = event_repo.list_events(limit=10)
	for event in recent_events:
		_decorate_event_for_display(event)

	return render_template(
		"dashboard.html",
		total_persons=total_persons,
		total_events=total_events,
		authorised_count=authorised_count,
		unauthorised_count=unauthorised_count,
		recent_events=recent_events,
		recognition_match_threshold=config.RECOGNITION_MATCH_THRESHOLD,
		authorisation_threshold=config.AUTHORISATION_THRESHOLD,
	)


@web_bp.route("/events")
@login_required
def events():
	_, event_repo, _ = _repos()
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
	_, event_repo, _ = _repos()
	event = event_repo.get_event_by_id(event_id)
	if event is None:
		abort(404)
	_decorate_event_for_display(event)
	snapshot_available = _resolve_snapshot_db_path(event.snapshot_path or "") is not None
	return render_template(
		"event.html",
		event=event,
		snapshot_available=snapshot_available,
		recognition_match_threshold=config.RECOGNITION_MATCH_THRESHOLD,
		authorisation_threshold=config.AUTHORISATION_THRESHOLD,
	)


@web_bp.route("/events/<event_id>/snapshot")
@login_required
def event_snapshot(event_id: str):
	"""
	Serve snapshots via event ID only.

	This prevents arbitrary file serving and constrains reads to snapshots dir.
	"""
	_, event_repo, _ = _repos()
	event = event_repo.get_event_by_id(event_id)
	if event is None or not event.snapshot_path:
		abort(404)

	resolved = _resolve_snapshot_db_path(event.snapshot_path)
	if resolved is None:
		abort(404)

	return send_file(resolved)


@web_bp.route("/persons")
@login_required
def persons():
	person_repo, _, _ = _repos()
	summaries = person_repo.list_person_summaries()
	return render_template("persons.html", persons=summaries)


@web_bp.route("/persons/<int:person_id>/delete", methods=["POST"])
@login_required
def delete_person(person_id: int):
	person_repo, _, _ = _repos()
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
