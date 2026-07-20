"""Sidecar lifecycle helpers: graceful shutdown for desktop packaging."""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

_shutdown_lock = threading.Lock()
_uvicorn_server: Any | None = None
_shutdown_requested = False


def set_uvicorn_server(server: Any) -> None:
    global _uvicorn_server
    with _shutdown_lock:
        _uvicorn_server = server


def shutdown_token() -> str | None:
    value = os.environ.get("STORYLENS_SHUTDOWN_TOKEN")
    return value.strip() if value else None


def request_shutdown(*, delay_seconds: float = 0.25) -> bool:
    """Ask the sidecar process to exit. Returns True if a stop was scheduled."""
    global _shutdown_requested
    with _shutdown_lock:
        if _shutdown_requested:
            return True
        _shutdown_requested = True
        server = _uvicorn_server

    if server is not None:
        server.should_exit = True
        return True

    # Frozen desktop sidecar without a Server handle: hard-exit after a brief delay.
    # Never os._exit the host interpreter during unit tests / non-frozen runs.
    if getattr(sys, "frozen", False):

        def _hard_exit() -> None:
            time.sleep(max(0.0, delay_seconds))
            os._exit(0)

        threading.Thread(target=_hard_exit, name="storylens-shutdown", daemon=True).start()
    return True


def reset_shutdown_state_for_tests() -> None:
    """Test-only: clear one-shot shutdown latch."""
    global _shutdown_requested, _uvicorn_server
    with _shutdown_lock:
        _shutdown_requested = False
        _uvicorn_server = None
