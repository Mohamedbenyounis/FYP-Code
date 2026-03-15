"""
Authentication utilities for web dashboard.
Iteration 5 minimal session auth.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import redirect, request, session, url_for


def login_required(view: Callable):
	"""Require a logged-in session for protected routes."""
	@wraps(view)
	def _wrapped(*args, **kwargs):
		if session.get("admin_username") is None:
			return redirect(url_for("web.login", next=request.path))
		return view(*args, **kwargs)

	return _wrapped


def login_user(admin_id: int, username: str) -> None:
	"""Store admin identity in session."""
	session["admin_id"] = admin_id
	session["admin_username"] = username


def logout_user() -> None:
	"""Clear admin identity from session."""
	session.pop("admin_id", None)
	session.pop("admin_username", None)
