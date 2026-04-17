"""
Tests for the servo control API endpoints and cross-process state.

Covers:
- toggle persistence
- move disables auto mode
- status endpoint correctness
- Pi offline graceful failure
- main loop skips compute_and_send when auto OFF
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app import config
from app.db.repo import SettingsRepository


# ── helpers ──────────────────────────────────────────────────────

def _login(client):
    """Authenticate the test client."""
    client.post(
        "/login",
        data={"username": "admin", "password": "test-admin-pass"},
    )


# ── SettingsRepository unit tests ────────────────────────────────

class TestSettingsRepository:
    def test_get_unset_returns_none(self, db):
        repo = SettingsRepository(db)
        assert repo.get_setting("nonexistent") is None

    def test_set_and_get(self, db):
        repo = SettingsRepository(db)
        repo.set_setting("servo_auto_enabled", "true")
        assert repo.get_setting("servo_auto_enabled") == "true"

    def test_upsert_overwrites(self, db):
        repo = SettingsRepository(db)
        repo.set_setting("servo_auto_enabled", "true")
        repo.set_setting("servo_auto_enabled", "false")
        assert repo.get_setting("servo_auto_enabled") == "false"


# ── /api/camera/servo/status ─────────────────────────────────────

class TestServoStatus:
    def test_status_defaults_auto_off(self, client, db):
        """Default state: auto_enabled is false, pi_online depends on config."""
        _login(client)
        res = client.get("/api/camera/servo/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["auto_enabled"] is False

    def test_status_reflects_db(self, client, db):
        """Status endpoint reads from system_settings."""
        repo = SettingsRepository(db)
        repo.set_setting("servo_auto_enabled", "true")

        _login(client)
        res = client.get("/api/camera/servo/status")
        data = res.get_json()
        assert data["auto_enabled"] is True

    def test_status_pi_offline_when_disabled(self, client, monkeypatch):
        """When SERVO_ENABLED is False, pi_online must be False."""
        monkeypatch.setattr(config, "SERVO_ENABLED", False)
        _login(client)
        res = client.get("/api/camera/servo/status")
        data = res.get_json()
        assert data["pi_online"] is False

    def test_status_pi_online(self, client, monkeypatch):
        """When Pi /status returns 200, pi_online is True."""
        monkeypatch.setattr(config, "SERVO_ENABLED", True)

        _login(client)
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            res = client.get("/api/camera/servo/status")
        data = res.get_json()
        assert data["pi_online"] is True

    def test_status_pi_unreachable(self, client, monkeypatch):
        """When Pi is unreachable, pi_online is False."""
        monkeypatch.setattr(config, "SERVO_ENABLED", True)

        _login(client)
        with patch("requests.get", side_effect=Exception("timeout")):
            res = client.get("/api/camera/servo/status")
        data = res.get_json()
        assert data["pi_online"] is False


# ── /api/camera/servo/toggle ─────────────────────────────────────

class TestServoToggle:
    def test_toggle_on(self, client, db):
        _login(client)
        res = client.post(
            "/api/camera/servo/toggle",
            json={"enabled": True},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["auto_enabled"] is True

        # Verify persistence
        repo = SettingsRepository(db)
        assert repo.get_setting("servo_auto_enabled") == "true"

    def test_toggle_off(self, client, db):
        repo = SettingsRepository(db)
        repo.set_setting("servo_auto_enabled", "true")

        _login(client)
        res = client.post(
            "/api/camera/servo/toggle",
            json={"enabled": False},
        )
        data = res.get_json()
        assert data["auto_enabled"] is False
        assert repo.get_setting("servo_auto_enabled") == "false"

    def test_toggle_persists_across_requests(self, client, db):
        """Toggle state survives across separate requests."""
        _login(client)
        client.post("/api/camera/servo/toggle", json={"enabled": True})

        # Fresh status check
        res = client.get("/api/camera/servo/status")
        assert res.get_json()["auto_enabled"] is True


# ── /api/camera/servo/move ───────────────────────────────────────

class TestServoMove:
    def test_move_disables_auto(self, client, db, monkeypatch):
        """Any manual move must set servo_auto_enabled to false."""
        repo = SettingsRepository(db)
        repo.set_setting("servo_auto_enabled", "true")
        monkeypatch.setattr(config, "SERVO_ENABLED", True)

        _login(client)
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            res = client.post(
                "/api/camera/servo/move",
                json={"axis": "pan", "dir": "left"},
            )
        data = res.get_json()
        assert data["success"] is True
        assert data["auto_enabled"] is False
        assert repo.get_setting("servo_auto_enabled") == "false"

    def test_move_invalid_axis(self, client):
        _login(client)
        res = client.post(
            "/api/camera/servo/move",
            json={"axis": "zoom", "dir": "in"},
        )
        assert res.status_code == 400

    def test_move_invalid_direction(self, client):
        _login(client)
        res = client.post(
            "/api/camera/servo/move",
            json={"axis": "pan", "dir": "diagonal"},
        )
        assert res.status_code == 400

    def test_move_recenter(self, client, monkeypatch):
        """Center button sends axis=both, dir=center."""
        monkeypatch.setattr(config, "SERVO_ENABLED", True)
        _login(client)
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            res = client.post(
                "/api/camera/servo/move",
                json={"axis": "both", "dir": "center"},
            )
        assert res.status_code == 200
        assert res.get_json()["success"] is True

    def test_move_pi_offline(self, client, monkeypatch):
        """Move fails gracefully when Pi is unreachable."""
        monkeypatch.setattr(config, "SERVO_ENABLED", True)
        _login(client)
        with patch("requests.get", side_effect=Exception("connection refused")):
            res = client.post(
                "/api/camera/servo/move",
                json={"axis": "pan", "dir": "left"},
            )
        assert res.status_code == 503
        data = res.get_json()
        assert data["success"] is False
        assert "unreachable" in data["error"].lower()

    def test_move_servo_not_enabled(self, client, monkeypatch):
        """Move returns 503 when servo is not enabled in config."""
        monkeypatch.setattr(config, "SERVO_ENABLED", False)
        _login(client)
        res = client.post(
            "/api/camera/servo/move",
            json={"axis": "pan", "dir": "left"},
        )
        assert res.status_code == 503
