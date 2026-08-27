"""Packaged desktop sidecar entry for StoryLens FastAPI.

Packaged with PyInstaller as ``storylens-api`` (``.exe`` on Windows).
Listens on 127.0.0.1 only.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def _prepare() -> None:
    api_root = Path(__file__).resolve().parent
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    # Frozen builds default to production data dir; source runs keep development.
    if getattr(sys, "frozen", False):
        os.environ.setdefault("STORYLENS_APP_ENV", "production")
    else:
        os.environ.setdefault("STORYLENS_APP_ENV", "development")
    from app.core.paths import apply_runtime_path_defaults

    try:
        layout = apply_runtime_path_defaults()
    except RuntimeError as exc:
        message = str(exc)
        if "DATA_DIR_NOT_WRITABLE" in message:
            logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
            logging.error(message)
            print(
                f"STORYLENS_SIDECAR_ERROR=DATA_DIR_NOT_WRITABLE:{message}",
                file=sys.stderr,
            )
            raise SystemExit(4) from exc
        raise
    log_dir = layout["logs"]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "sidecar.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )
    logging.getLogger(__name__).info(
        "StoryLens sidecar starting data_dir=%s database_url=%s",
        layout["root"],
        os.environ.get("STORYLENS_DATABASE_URL"),
    )


def main() -> int:
    _prepare()
    import uvicorn

    host = os.environ.get("STORYLENS_APP_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        logging.error("Refusing to bind non-loopback host: %s", host)
        return 2
    try:
        port = int(os.environ.get("STORYLENS_APP_PORT", "8000"))
    except ValueError:
        logging.error("Invalid STORYLENS_APP_PORT")
        return 2

    try:
        from app.core.sidecar_control import set_uvicorn_server

        # StoryLens does not use WebSocket (task progress is HTTP polling).
        # Disable WS so a broken optional `websockets` install cannot block boot.
        config = uvicorn.Config(
            "app.main:app",
            host=host,
            port=port,
            log_level="info",
            access_log=False,
            log_config=None,
            ws="none",
        )
        server = uvicorn.Server(config)
        set_uvicorn_server(server)
        server.run()
    except OSError as exc:
        logging.exception("Backend bind/start failed: %s", exc)
        # Structured token for Tauri / UI mapping
        print(f"STORYLENS_SIDECAR_ERROR=PORT_OR_BIND_FAILED:{exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 — last-resort sidecar boundary
        logging.exception("Backend crashed: %s", exc)
        print(f"STORYLENS_SIDECAR_ERROR=START_FAILED:{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
