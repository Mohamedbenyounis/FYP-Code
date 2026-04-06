from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app import config
from app.core.models import Event
from app.db.repo import SQLiteEventRepository, SQLitePersonRepository
from app.web.app_factory import create_app


def _set_bootstrap_admin_env(monkeypatch) -> None:
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "test-admin-pass")


def _login(client) -> None:
    res = client.post(
        "/login",
        data={"username": "admin", "password": "test-admin-pass"},
        follow_redirects=False,
    )
    assert res.status_code in (302, 303)


def _insert_event(
    event_repo: SQLiteEventRepository,
    snapshot_path: str | None = None,
    status: str = "unauthorised",
    person_name: str | None = None,
    score: float = 0.0,
) -> str:
    event_id = str(uuid4())
    event_repo.add_event(
        Event(
            event_id=event_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            person_name=person_name,
            person_id=None,
            score=score,
            bbox_json=None,
            snapshot_path=snapshot_path,
            clip_path=None,
            track_key=None,
        )
    )
    return event_id


def _insert_person(person_repo: SQLitePersonRepository, name: str = "Alice") -> int:
    import numpy as np

    emb = np.zeros(512, dtype=np.float32)
    person = person_repo.add_person(name=name, embedding=emb)
    return person.person_id


def test_auth_protection_redirects_to_login(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", tmp_path / "data" / "snapshots")

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    client = app.test_client()

    res = client.get("/", follow_redirects=False)
    assert res.status_code in (301, 302)
    assert "/login" in res.headers["Location"]


def test_events_list_route(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", tmp_path / "data" / "snapshots")

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    conn = app.config["DB_CONN"]
    event_repo = SQLiteEventRepository(conn)
    event_id = _insert_event(event_repo)

    client = app.test_client()
    _login(client)

    res = client.get("/events")
    assert res.status_code == 200
    assert event_id.encode("utf-8") in res.data


def test_event_detail_route(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", tmp_path / "data" / "snapshots")

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    conn = app.config["DB_CONN"]
    event_repo = SQLiteEventRepository(conn)
    event_id = _insert_event(event_repo)

    client = app.test_client()
    _login(client)

    res = client.get(f"/events/{event_id}")
    assert res.status_code == 200
    assert event_id.encode("utf-8") in res.data


def test_persons_list_route_safe_metadata(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", tmp_path / "data" / "snapshots")

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    conn = app.config["DB_CONN"]
    person_repo = SQLitePersonRepository(conn)
    _insert_person(person_repo, "Alice")

    client = app.test_client()
    _login(client)

    res = client.get("/persons")
    assert res.status_code == 200
    assert b"Alice" in res.data
    # Ensure raw embedding bytes are not shown.
    assert b"float32" not in res.data


def test_snapshot_route_serves_only_from_snapshot_dir(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    base_dir = tmp_path
    snapshots_dir = base_dir / "data" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", base_dir)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", snapshots_dir)

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    conn = app.config["DB_CONN"]
    event_repo = SQLiteEventRepository(conn)

    good_rel = Path("data") / "snapshots" / "test.jpg"
    good_abs = base_dir / good_rel
    good_abs.parent.mkdir(parents=True, exist_ok=True)
    good_abs.write_bytes(b"jpeg-bytes")

    good_event_id = _insert_event(event_repo, snapshot_path=str(good_rel))
    bad_event_id = _insert_event(event_repo, snapshot_path="..\\..\\Windows\\win.ini")

    client = app.test_client()
    _login(client)

    ok = client.get(f"/events/{good_event_id}/snapshot")
    assert ok.status_code == 200

    blocked = client.get(f"/events/{bad_event_id}/snapshot")
    assert blocked.status_code == 404


def test_snapshot_route_serves_windows_style_relative_path(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    base_dir = tmp_path
    snapshots_dir = base_dir / "data" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", base_dir)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", snapshots_dir)

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    conn = app.config["DB_CONN"]
    event_repo = SQLiteEventRepository(conn)

    good_abs = snapshots_dir / "win-style.jpg"
    good_abs.write_bytes(b"jpeg-bytes")

    # Simulate a DB row written on Windows with backslash separators.
    win_rel = "data\\snapshots\\win-style.jpg"
    event_id = _insert_event(event_repo, snapshot_path=win_rel)

    client = app.test_client()
    _login(client)

    res = client.get(f"/events/{event_id}/snapshot")
    assert res.status_code == 200


def test_named_unauthorised_event_shows_low_confidence_explanation(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", tmp_path / "data" / "snapshots")

    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    conn = app.config["DB_CONN"]
    event_repo = SQLiteEventRepository(conn)
    event_id = _insert_event(
        event_repo,
        status="unauthorised",
        person_name="Mohamed",
        score=0.333,
    )

    client = app.test_client()
    _login(client)

    events_res = client.get("/events")
    assert events_res.status_code == 200
    assert b"Mohamed" in events_res.data
    assert b"Matched identity but unauthorised (low confidence)." in events_res.data

    detail_res = client.get(f"/events/{event_id}")
    assert detail_res.status_code == 200
    assert b"Matched identity but unauthorised (low confidence)." in detail_res.data


def test_clip_route_serves_only_from_clip_dir(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    base_dir = tmp_path
    clips_dir = base_dir / "data" / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", base_dir)
    monkeypatch.setattr(config, "CLIPS_DIR", clips_dir)
    
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    # Overwrite app config so our route resolver works 
    app.config["CLIPS_DIR"] = clips_dir
    
    conn = app.config["DB_CONN"]
    event_repo = SQLiteEventRepository(conn)

    good_rel = Path("data") / "clips" / "test_clip.mp4"
    good_abs = base_dir / good_rel
    good_abs.parent.mkdir(parents=True, exist_ok=True)
    good_abs.write_bytes(b"mp4-bytes")

    # Manually insert event with clip_path
    event_id_good = str(uuid4())
    event_repo.add_event(Event(event_id_good, datetime.now(timezone.utc).isoformat(), "authorised", None, None, 0.0, None, None, str(good_rel), None))
    
    event_id_bad = str(uuid4())
    event_repo.add_event(Event(event_id_bad, datetime.now(timezone.utc).isoformat(), "authorised", None, None, 0.0, None, None, "..\\..\\Windows\\sys32.dll", None))

    client = app.test_client()
    _login(client)

    ok = client.get(f"/events/{event_id_good}/clip")
    assert ok.status_code == 200

    blocked = client.get(f"/events/{event_id_bad}/clip")
    assert blocked.status_code == 404


def test_live_frame_route(tmp_path, monkeypatch):
    _set_bootstrap_admin_env(monkeypatch)
    db_path = tmp_path / "securevision.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    client = app.test_client()
    _login(client)

    # Missing pipeline implies main isn't running yet, should 503
    missing_res = client.get("/live/frame")
    assert missing_res.status_code == 503

    # Simulate main pipeline writing a frame to active RAM
    from multiprocessing import shared_memory
    payload = b"fake-image"
    size = len(payload)
    shm = None
    try:
        shm = shared_memory.SharedMemory(name="sv_live_frame", create=True, size=1024)
        shm.buf[0] = 0
        shm.buf[1:5] = size.to_bytes(4, 'little')
        shm.buf[5:9] = (1).to_bytes(4, 'little')  # seq=1
        import struct
        import time
        shm.buf[9:17] = struct.pack('<d', time.monotonic())
        shm.buf[17:17+size] = payload
        
        ok_res = client.get("/live/frame")
        assert ok_res.status_code == 200
        assert ok_res.headers.get("Cache-Control") == "no-store, no-cache, must-revalidate, max-age=0"
    finally:
        if shm is not None:
            shm.close()
            shm.unlink()
