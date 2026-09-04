"""Root-only installation/activation; never invokes Docker or reads runtime secrets."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_policy import DeployError, scan_secret, valid_path
from deploy_protocol import PROTOCOL, TOOL_FILES, tool_version, trusted

LIB = Path("/opt/storylens/lib/storylens-online-deploy")
BIN = Path("/opt/storylens/bin/storylens-online-deploy-lightweight")
LOCK_ROOT = Path("/run/lock/storylens-online-deploy")
COMMIT_PATTERN = r"[0-9a-f]{40}"
LEGACY_LOCK_PATTERN = r"sl-accept-[a-z0-9]{8,24}\.lock"
# Frozen original protocol-2 layout; never derive old manifests from today's files.
LEGACY_TOOL_FILES = (
    "deploy-lightweight.sh",
    "deploy_protocol.py",
    "deploy_cli.py",
    "deploy_install.py",
    "deploy_runtime.py",
    "deploy_policy.py",
    "deploy_package.py",
    "deploy_acceptance.py",
    "deploy_bootstrap.py",
)


def verify_source(source: Path) -> dict:
    if not source.is_absolute() or source != source.resolve(strict=True):
        raise DeployError("INVALID_BOOTSTRAP_PATH")
    trusted(source)
    trusted(source / "bootstrap.json")
    meta = json.loads((source / "bootstrap.json").read_text())
    if meta["protocol"] != PROTOCOL or not re.fullmatch(r"[0-9a-f]{40}", meta["commit"]):
        raise DeployError("INVALID_BOOTSTRAP")
    for name, digest in meta["files"].items():
        if (
            not valid_path(name)
            or not (
                name
                in {"VERSION", "scripts/deploy_online.ps1", "release/changes/CHG-20260903-001.json"}
                or name.startswith(("apps/online_api/", "apps/online_web/", "infra/online/"))
            )
            or any(
                part
                in {
                    ".env",
                    "online.env",
                    "node_modules",
                    "uploads",
                    "pb_data",
                    ".venv",
                    "__pycache__",
                }
                for part in name.split("/")
            )
        ):
            raise DeployError("INVALID_BOOTSTRAP")
        path = source / name
        trusted(path)
        if (
            not path.is_file()
            or path.stat().st_nlink != 1
            or path.stat().st_size > 16 * 1024 * 1024
        ):
            raise DeployError("SOURCE_HASH_MISMATCH")
        value = path.read_bytes()
        scan_secret(value)
        if hashlib.sha256(value).hexdigest() != digest:
            raise DeployError("SOURCE_HASH_MISMATCH")
    if meta["tool_version"] != tool_version(source / "infra/online"):
        raise DeployError("PROTOCOL_MISMATCH")
    return meta


def installed(directory: Path) -> dict:
    trusted(directory)
    if not re.fullmatch(COMMIT_PATTERN, directory.name) or not directory.is_dir():
        raise DeployError("UNKNOWN_INSTALLED_VERSION")
    names = {p.name for p in directory.iterdir()}
    layout = next(
        (files for files in (TOOL_FILES, LEGACY_TOOL_FILES) if names == {*files, "installed.json"}),
        None,
    )
    if layout is None:
        raise DeployError("UNKNOWN_INSTALLED_VERSION")
    for name in (*layout, "installed.json"):
        path = directory / name
        trusted(path)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise DeployError("UNKNOWN_INSTALLED_VERSION")
    digest = hashlib.sha256()
    for name in sorted(layout):
        digest.update(name.encode() + b"\0" + (directory / name).read_bytes() + b"\0")
    meta = json.loads((directory / "installed.json").read_text())
    if (
        meta["commit"] != directory.name
        or meta["protocol"] != PROTOCOL
        or meta["tool_version"] != digest.hexdigest()
    ):
        raise DeployError("UNKNOWN_INSTALLED_VERSION")
    return meta


def check_lock_info(info) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise DeployError("INVALID_LOCK_FILE")


def validate_lock(path: Path) -> None:
    info = path.lstat()  # never open/read/follow a legacy lock
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise DeployError("INVALID_LOCK_FILE")
    if os.name != "nt":
        check_lock_info(info)


def registry(lib: Path = LIB) -> dict:
    trusted(lib)
    versions, locks = [], []
    for path in sorted(lib.iterdir()):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode) and re.fullmatch(COMMIT_PATTERN, path.name):
            versions.append(installed(path))
        elif re.fullmatch(LEGACY_LOCK_PATTERN, path.name):
            validate_lock(path)
            locks.append(path.name)
        else:
            raise DeployError("UNKNOWN_REGISTRY_ENTRY")
    return {"versions": versions, "legacy_locks": locks}


def entry_target(lib: Path, entry: Path, records: dict) -> Path | None:
    trusted(entry.parent)
    if not entry.exists() and not entry.is_symlink():
        return None
    info = entry.lstat()
    if not stat.S_ISLNK(info.st_mode) or (os.name != "nt" and (info.st_uid or info.st_gid)):
        raise DeployError("UNKNOWN_INSTALLED_VERSION")
    target = entry.resolve(strict=True) if os.name == "nt" else Path(os.readlink(entry))
    if target not in {lib / m["commit"] / "deploy-lightweight.sh" for m in records["versions"]}:
        raise DeployError("UNKNOWN_INSTALLED_VERSION")
    return target


def registry_selfcheck(lib: Path, entry: Path, target: Path | None) -> None:
    if entry_target(lib, entry, registry(lib)) != target:
        raise DeployError("REGISTRY_SELFCHECK_FAILED")


def atomic_entry(entry: Path, target: Path | None) -> None:
    if target is None:
        entry.unlink()
    else:
        temporary = entry.with_name(entry.name + f".new-{time.time_ns()}")
        os.symlink(target, temporary)
        os.replace(temporary, entry)


def switch_entry(target: Path | None, lib: Path, entry: Path) -> None:
    records = registry(lib)
    old = entry_target(lib, entry, records)
    registry_selfcheck(lib, entry, old)  # equivalent list check before activation
    if old is not None:
        backup = entry.parent / f"previous-tool-{time.time_ns()}.json"
        with backup.open("x") as stream:
            json.dump(installed(old.parent), stream)
        backup.chmod(0o400)
    changed = False
    try:
        atomic_entry(entry, target)
        changed = True
        registry_selfcheck(lib, entry, target)
    except BaseException:  # noqa: BLE001 -- restore entry even on interruption
        switched = (target is None and not entry.exists() and not entry.is_symlink()) or (
            target is not None and entry.is_symlink() and entry.resolve() == target
        )
        if changed or switched:
            try:
                atomic_entry(entry, old)
            except BaseException:  # noqa: BLE001 -- never expose rollback errors
                raise DeployError("ENTRY_RESTORE_FAILED_MANUAL_RECOVERY_REQUIRED") from None
        raise DeployError("REGISTRY_SELFCHECK_FAILED_ENTRY_RESTORED") from None


def activate(commit: str, lib: Path = LIB, entry: Path = BIN) -> None:
    records = registry(lib)
    if commit not in {m["commit"] for m in records["versions"]}:
        raise DeployError("INVALID_VERSION")
    switch_entry(lib / commit / "deploy-lightweight.sh", lib, entry)


def unlink(commit: str, lib: Path = LIB, entry: Path = BIN) -> None:
    records = registry(lib)
    if (
        not re.fullmatch(COMMIT_PATTERN, commit)
        or entry_target(lib, entry, records) != lib / commit / "deploy-lightweight.sh"
    ):
        raise DeployError("UNKNOWN_INSTALLED_VERSION")
    switch_entry(None, lib, entry)


@contextmanager
def operation_lock(name: str, root: Path = LOCK_ROOT):
    """Dedicated root-only lock storage; retain files and never truncate them."""
    if not (re.fullmatch(LEGACY_LOCK_PATTERN, name) or name == "registry.lock"):
        raise DeployError("INVALID_LOCK_FILE")
    # /run/lock itself can be 1777; create our root-owned 0700 leaf atomically,
    # then reject substitution/ownership problems. Never chmod an existing path.
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for parent in root.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or (
            os.name != "nt"
            and (
                info.st_uid
                or info.st_gid
                or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)
            )
        ):
            raise DeployError("INVALID_LOCK_DIRECTORY")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or (
        os.name != "nt" and (info.st_uid or info.st_gid or stat.S_IMODE(info.st_mode) != 0o700)
    ):
        raise DeployError("INVALID_LOCK_DIRECTORY")
    path = root / name
    if path.exists() or path.is_symlink():
        validate_lock(path)
    import fcntl

    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if os.name != "nt":
            check_lock_info(os.fstat(descriptor))
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def install(source: Path, lib: Path = LIB, entry: Path = BIN) -> dict:
    meta = verify_source(source)
    for directory in (lib, entry.parent):
        directory.mkdir(parents=True, exist_ok=True, mode=0o755)
        trusted(directory)
    registry(lib)  # identical validation for install/list/activate/unlink
    target = lib / meta["commit"]
    if target.exists():
        if installed(target)["tool_version"] != meta["tool_version"]:
            raise DeployError("UNKNOWN_INSTALLED_VERSION")
    else:
        target.mkdir(mode=0o755)
        for name in TOOL_FILES:
            value = (source / "infra/online" / name).read_bytes()
            with (target / name).open("xb") as stream:
                stream.write(value)
            (target / name).chmod(0o555 if name.endswith(".sh") else 0o444)
        record = {k: meta[k] for k in ("commit", "protocol", "tool_version")}
        with (target / "installed.json").open("x") as stream:
            json.dump(record, stream)
        (target / "installed.json").chmod(0o444)
    activate(meta["commit"], lib, entry)
    return installed(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "list", "activate", "unlink"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise DeployError("ROOT_REQUIRED")
        os.umask(0o077)
        with operation_lock("registry.lock"):
            if args.action == "install":
                print(json.dumps(install(args.source)))
            elif args.action == "activate":
                activate(args.commit)
                print("TOOL_ACTIVATED")
            elif args.action == "list":
                print(json.dumps(registry()))
            else:
                unlink(args.commit)
                print("ENTRY_UNLINKED_VERSIONS_RETAINED")
        return 0
    except Exception:  # noqa: BLE001 -- privileged CLI redaction
        print("TOOL_INSTALL_FAILED_SAFELY")
        return 1


if __name__ == "__main__":
    sys.exit(main())
