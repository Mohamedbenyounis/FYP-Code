"""
Flask application factory.
Iteration 5 dashboard implementation.
"""

from typing import Optional

from flask import Flask

from app import config
from app.db.migrations import init_db
from app.services.logging_service import get_logger
from app.web.routes import web_bp


def create_app(config_override: Optional[dict] = None):
    """Create and configure Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = config.FLASK_SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    if config_override:
        app.config.update(config_override)

    # The dashboard owns its own DB connection (separate process from pipeline).
    app.config["DB_CONN"] = init_db(config.DB_PATH)
    app.config["SNAPSHOTS_DIR"] = config.SNAPSHOTS_DIR

    app.register_blueprint(web_bp)

    log = get_logger()
    if config.FLASK_SECRET_KEY == "securevision-dev-secret":
        log.warning("SECURITY: SV_FLASK_SECRET_KEY not set; using dev secret")

    @app.template_filter('local_time')
    def local_time_filter(iso_str):
        if not iso_str:
            return "Unknown"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(iso_str)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(iso_str).split('.')[0]

    return app
