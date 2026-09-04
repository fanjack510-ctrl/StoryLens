"""Protocol and content-addressed tool identity, independent of business releases."""

import hashlib
import os
from pathlib import Path

PROTOCOL = 2
TOOL_FILES = (
    "deploy-lightweight.sh",
    "deploy_protocol.py",
    "deploy_cli.py",
    "deploy_install.py",
    "deploy_runtime.py",
    "deploy_policy.py",
    "deploy_package.py",
    "deploy_acceptance.py",
    "deploy_bootstrap.py",
    "deploy_image_contract.py",
    "deploy_image_probe.py",
)


def tool_version(directory: Path) -> str:
    digest = hashlib.sha256()
    for name in sorted(TOOL_FILES):
        digest.update(name.encode() + b"\0" + (directory / name).read_bytes() + b"\0")
    return digest.hexdigest()


def trusted(path: Path) -> None:
    """No symlinks or writable/unowned ancestors at a privileged boundary."""
    for item in (path, *path.parents):
        info = item.lstat()
        if item.is_symlink() or (
            os.name != "nt" and (info.st_uid or info.st_gid or info.st_mode & 0o022)
        ):
            raise ValueError("UNTRUSTED_PATH")


def check_protocol(protocol: int, expected: str, directory: Path) -> None:
    from deploy_policy import DeployError

    if protocol != PROTOCOL or expected != tool_version(directory):
        raise DeployError("PROTOCOL_MISMATCH")
