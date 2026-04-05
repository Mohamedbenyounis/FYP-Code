"""
Authentication utilities for web dashboard.
Iteration 5 minimal session auth + Iteration 13 RBAC.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import abort, redirect, request, session, url_for


def login_required(view: Callable):
	"""Require a logged-in session for protected routes."""
	@wraps(view)
	def _wrapped(*args, **kwargs):
		if session.get("user_id") is None:
			return redirect(url_for("web.login", next=request.path))
		return view(*args, **kwargs)

	return _wrapped


def role_required(allowed_roles: list[str]):
	"""Require the logged-in user to have a specific role."""
	def decorator(view: Callable):
		@wraps(view)
		def _wrapped(*args, **kwargs):
			# 1. Authentication check: Must be logged in
			if not session.get("user_id"):
				return redirect(url_for("web.login"))
			
			# 2. Authorisation check: Must have correct role
			if session.get("role") not in allowed_roles:
				abort(403)  # Explicit Forbidden for security justification
				
			return view(*args, **kwargs)
		return _wrapped
	return decorator


def login_user(user_id: int, username: str, role: str) -> None:
	"""Store user identity and role in session."""
	session["user_id"] = user_id
	session["username"] = username
	session["role"] = role


def logout_user() -> None:
	"""Clear user identity from session."""
	session.pop("user_id", None)
	session.pop("username", None)
	session.pop("role", None)
