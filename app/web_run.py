"""SecureVision dashboard entry point (Iteration 5)."""

from __future__ import annotations

from app import config
from app.services.logging_service import get_logger
from app.web.app_factory import create_app


def main() -> int:
    log = get_logger()
    app = create_app()

    log.info("Dashboard starting at http://%s:%d", config.DASHBOARD_HOST, config.DASHBOARD_PORT)
    app.run(host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
