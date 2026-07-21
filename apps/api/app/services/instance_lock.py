"""Single-instance lock so only one StoryLens writer owns the local DB."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.core.paths import ensure_user_data_dirs, user_data_root


def lock_path() -> Path:
    root = ensure_user_data_dirs()["root"]
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime / "storylens_instance.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except Exception:  # noqa: BLE001
        return False
    return True


def read_lock() -> dict | None:
    path = lock_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    return data


def acquire_instance_lock(*, port: int, shell: str) -> dict:
    """Acquire or reclaim lock. Raises RuntimeError if another live owner exists."""
    existing = read_lock()
    pid = os.getpid()
    if existing:
        owner = int(existing.get("pid") or 0)
        if owner and owner != pid and _pid_alive(owner):
            raise RuntimeError(
                f"STORYLENS_ALREADY_RUNNING: PID {owner} already owns the local instance "
                f"(port={existing.get('port')})."
            )
    payload = {
        "pid": pid,
        "port": port,
        "shell": shell,
        "data_directory": str(user_data_root()),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    lock_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def release_instance_lock() -> None:
    path = lock_path()
    existing = read_lock()
    if existing and int(existing.get("pid") or 0) not in {0, os.getpid()}:
        return
    path.unlink(missing_ok=True)
