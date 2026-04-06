import pytest
from pathlib import Path
from app import config
from app.web.app_factory import create_app

@pytest.fixture
def test_dir(tmp_path, monkeypatch):
    """Setup a safe temporary environment for DB and files."""
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "test-admin-pass")
    
    db_path = tmp_path / "securevision.sqlite"
    snapshots_dir = tmp_path / "data" / "snapshots"
    clips_dir = tmp_path / "data" / "clips"
    
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", snapshots_dir)
    monkeypatch.setattr(config, "CLIPS_DIR", clips_dir)
    
    return tmp_path

@pytest.fixture
def app(test_dir):
    """Create a Flask application for testing."""
    _app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    _app.config["CLIPS_DIR"] = config.CLIPS_DIR
    return _app

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def db(app):
    """Returns the raw DB connection populated by init_db in create_app."""
    return app.config["DB_CONN"]
