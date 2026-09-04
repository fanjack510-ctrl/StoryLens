"""Stdlib-only, secret-free image probe; runs as the final application's UID."""

import contextlib
import hashlib
import importlib
import io
import json
import logging
import os
import sys
from pathlib import Path

MODULES = (
    "storylens_online.main",
    "storylens_online.worker",
    "storylens_online.db.init_schema",
    "storylens_online.db.models",
    "storylens_online.db.phase2b1_migration",
)


def inspect_runtime(package: Path, entrypoint: Path) -> dict:
    files = {}
    for directory, dirs, names in os.walk(
        package, onerror=lambda error: (_ for _ in ()).throw(error)
    ):
        parent = Path(directory)
        assert not parent.is_symlink()
        assert (parent / "__init__.py").is_file()  # no silent namespace fallback
        assert os.access(parent, os.R_OK | os.X_OK)
        for name in dirs:
            assert not (parent / name).is_symlink()
        for name in names:
            path = parent / name
            assert path.is_file() and not path.is_symlink()
            files[path.relative_to(package).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    assert files and entrypoint.is_file() and not entrypoint.is_symlink()
    assert os.access(entrypoint, os.R_OK | os.X_OK)
    for name in MODULES:
        module = importlib.import_module(name)
        assert module.__file__ and Path(module.__file__).resolve().is_relative_to(package.resolve())
    return {
        "status": "IMAGE_RUNTIME_CONTRACT_OK",
        "files": files,
        "entrypoint": hashlib.sha256(entrypoint.read_bytes()).hexdigest(),
        "modules": list(MODULES),
    }


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        assert os.getuid() == 10001 and os.getgid() == 10001
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = inspect_runtime(
                Path("/srv/storylens-online/storylens_online"),
                Path("/usr/local/bin/storylens-online-worker-entrypoint"),
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except BaseException:  # noqa: BLE001 -- never emit import errors or environment
        print("IMAGE_RUNTIME_CONTRACT_FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
