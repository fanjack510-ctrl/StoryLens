"""Manifest-exact source trees and post-build non-root runtime verification."""

import hashlib
import json
import os
import re
import stat
from pathlib import Path

from deploy_image_probe import MODULES
from deploy_policy import DeployError
from deploy_protocol import trusted

PACKAGE = "apps/online_api/storylens_online/"
ENTRYPOINT = "infra/online/worker-entrypoint.sh"


def copy_context(source: Path, destination: Path, manifest: dict) -> None:
    """Normalize *only* public build source modes, never state or Secret parents."""
    destination.mkdir(parents=True, exist_ok=True)
    for name, expected in manifest.items():
        value = (source / name).read_bytes()
        if hashlib.sha256(value).hexdigest() != expected:
            raise DeployError("BUILD_CONTEXT_CONTRACT_FAILED")
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
        path.chmod(0o555 if name.endswith(".sh") else 0o444)
    # Explicit chmod after mkdir: mode=0755 alone is masked to 0700 by umask 077.
    for path in [destination, *(p for p in destination.rglob("*") if p.is_dir())]:
        path.chmod(0o755)
    context_contract(destination, manifest)


def context_contract(source: Path, manifest: dict) -> dict:
    try:
        actual = {}
        for path in source.rglob("*"):
            trusted(path)
            if path.name == ".dockerignore" or path.name.endswith(".dockerignore"):
                # This closed context needs no exclusions; don't approximate Docker's glob rules.
                raise ValueError
            if path.is_dir():
                if not any(path.iterdir()):
                    raise ValueError
                if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != 0o755:
                    raise ValueError
            elif path.is_file():
                actual[path.relative_to(source).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                if os.name != "nt" and path.stat().st_mode & 0o044 != 0o044:
                    raise ValueError
            else:
                raise ValueError
        if actual != manifest:
            raise ValueError
        runtime = {n.removeprefix(PACKAGE): h for n, h in actual.items() if n.startswith(PACKAGE)}
        required = {
            "__init__.py",
            *(n.replace(".", "/").removeprefix("storylens_online/") + ".py" for n in MODULES),
        }
        if not required <= runtime.keys() or ENTRYPOINT not in actual:
            raise ValueError
        for name in runtime:
            for directory in Path(name).parents:
                initializer = (directory / "__init__.py").as_posix()
                if initializer not in runtime:
                    raise ValueError
        return {"files": runtime, "entrypoint": actual[ENTRYPOINT]}
    except Exception:  # noqa: BLE001 -- no source/credential values in errors
        raise DeployError("BUILD_CONTEXT_CONTRACT_FAILED") from None


def verify_image(runner, image: str, expected: dict) -> dict:
    try:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError
        probe = Path(__file__).with_name("deploy_image_probe.py").read_text(encoding="utf-8")
        result = json.loads(
            runner(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--user",
                    "10001:10001",
                    "--entrypoint",
                    "python",
                    "--workdir",
                    "/srv/storylens-online",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,nodev,size=1m,mode=1777",
                    "--env",
                    "STORYLENS_ONLINE_PHASE2B1_ENABLED=false",
                    "--env",
                    "STORYLENS_ONLINE_UPLOAD_DIR=/tmp/contract-uploads",
                    image,
                    "-E",
                    "-B",
                    "-c",
                    probe,
                ],
                timeout=120,
            )
        )
        if result != {"status": "IMAGE_RUNTIME_CONTRACT_OK", **expected, "modules": list(MODULES)}:
            raise ValueError
        return {"status": "IMAGE_RUNTIME_CONTRACT_OK", "image": image, **expected}
    except Exception:  # noqa: BLE001 -- suppress Docker/import output, keep evidence safe
        raise DeployError("IMAGE_RUNTIME_CONTRACT_FAILED") from None
