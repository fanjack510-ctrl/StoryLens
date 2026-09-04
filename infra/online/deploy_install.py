"""Root-only installation/activation; never invokes Docker or reads runtime secrets."""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_policy import DeployError, scan_secret, valid_path
from deploy_protocol import PROTOCOL, TOOL_FILES, tool_version, trusted

LIB = Path("/opt/storylens/lib/storylens-online-deploy")
BIN = Path("/opt/storylens/bin/storylens-online-deploy-lightweight")


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
    for name in (*TOOL_FILES, "installed.json"):
        trusted(directory / name)
    meta = json.loads((directory / "installed.json").read_text())
    if (
        meta["commit"] != directory.name
        or meta["protocol"] != PROTOCOL
        or meta["tool_version"] != tool_version(directory)
    ):
        raise DeployError("UNKNOWN_INSTALLED_VERSION")
    return meta


def activate(commit: str, lib: Path = LIB, entry: Path = BIN) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DeployError("INVALID_VERSION")
    installed(lib / commit)
    trusted(entry.parent)
    if entry.exists() or entry.is_symlink():
        if not entry.is_symlink():
            raise DeployError("UNKNOWN_INSTALLED_VERSION")
        old = entry.resolve(strict=True)
        if old.parent.parent != lib or old.name != "deploy-lightweight.sh":
            raise DeployError("UNKNOWN_INSTALLED_VERSION")
        previous = installed(old.parent)
        backup = entry.parent / f"previous-tool-{time.time_ns()}.json"
        with backup.open("x") as stream:
            json.dump(previous, stream)
        backup.chmod(0o400)
    temporary = entry.with_name(entry.name + ".new")
    os.symlink(lib / commit / "deploy-lightweight.sh", temporary)
    os.replace(temporary, entry)


def install(source: Path, lib: Path = LIB, entry: Path = BIN) -> dict:
    meta = verify_source(source)
    for directory in (lib, entry.parent):
        directory.mkdir(parents=True, exist_ok=True, mode=0o755)
        trusted(directory)
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
        if args.action == "install":
            print(json.dumps(install(args.source)))
        elif args.action == "activate":
            activate(args.commit)
            print("TOOL_ACTIVATED")
        elif args.action == "list":
            print(json.dumps([installed(p) for p in sorted(LIB.iterdir()) if p.is_dir()]))
        else:
            installed(LIB / args.commit)
            if not BIN.is_symlink() or BIN.resolve() != LIB / args.commit / "deploy-lightweight.sh":
                raise DeployError("UNKNOWN_INSTALLED_VERSION")
            BIN.unlink()
            print("ENTRY_UNLINKED_VERSIONS_RETAINED")
        return 0
    except Exception:  # noqa: BLE001 -- privileged CLI redaction
        print("TOOL_INSTALL_FAILED_SAFELY")
        return 1


if __name__ == "__main__":
    sys.exit(main())
