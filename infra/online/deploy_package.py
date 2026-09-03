"""Build minimal source bundles from git archive, never the working directory."""

import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from deploy_policy import (
    BUILD,
    MODULE,
    SUPPORT,
    DeployError,
    require_mode,
    safe_payload_path,
    scan_secret,
    valid_path,
)

MAX_BYTES = 128 * 1024 * 1024


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False, timeout=120
    )
    if result.returncode:
        raise DeployError("GIT_CHECK_FAILED")
    return result.stdout


def preflight(root: Path, mode: str, baseline: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{7,40}", baseline):
        raise DeployError("INVALID_BASELINE")
    if git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise DeployError("WORKTREE_NOT_CLEAN")
    commit = git(root, "rev-parse", "HEAD^{commit}").decode().strip()
    baseline = git(root, "rev-parse", f"{baseline}^{{commit}}").decode().strip()
    git(root, "merge-base", "--is-ancestor", baseline, commit)
    paths = git(root, "diff", "--no-renames", "--name-only", "-z", baseline, commit)
    changed = [name.decode("utf-8") for name in paths.split(b"\x00") if name]
    require_mode(changed, mode)
    version = git(root, "show", f"{commit}:VERSION").strip()
    if version != b"1.3.6" or git(root, "show", f"{baseline}:VERSION").strip() != version:
        raise DeployError("VERSION_MISMATCH")
    return {"commit": commit, "baseline": baseline, "mode": mode, "changed": changed}


def members(data: bytes, mode: str) -> dict[str, tuple[bytes, int]]:
    if len(data) > MAX_BYTES:
        raise DeployError("PACKAGE_TOO_LARGE")
    contents = {}
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        for item in archive:
            name = item.name.rstrip("/") if item.isdir() else item.name
            if not valid_path(name) or name.lower() in seen:
                raise DeployError("INVALID_ARCHIVE")
            seen.add(name.lower())
            if len(seen) > 5000:
                raise DeployError("PACKAGE_TOO_LARGE")
            if item.isdir():
                allowed = (*SUPPORT, *BUILD[mode], MODULE[mode])
                if not any(path.startswith(name + "/") for path in allowed) and not (
                    name + "/"
                ).startswith(MODULE[mode]):
                    raise DeployError("INVALID_ARCHIVE")
                continue
            if not item.isfile() or item.mode & 0o7000:
                raise DeployError("INVALID_ARCHIVE")
            if name != "deployment.json" and not safe_payload_path(name, mode):
                raise DeployError("INVALID_ARCHIVE")
            total += item.size
            if total > MAX_BYTES or len(contents) >= 5000:
                raise DeployError("PACKAGE_TOO_LARGE")
            stream = archive.extractfile(item)
            if stream is None:
                raise DeployError("INVALID_ARCHIVE")
            content = stream.read()
            scan_secret(content)
            contents[name] = (content, 0o755 if item.mode & 0o111 else 0o644)
    return contents


def fingerprints(contents: dict[str, tuple[bytes, int]]) -> dict:
    return {
        name: {"sha256": hashlib.sha256(data).hexdigest()}
        for name, (data, _mode) in sorted(contents.items())
    }


def source(root: Path, revision: str, mode: str) -> dict:
    paths = [MODULE[mode].rstrip("/"), *BUILD[mode], *SUPPORT]
    data = git(root, "archive", "--format=tar", revision, "--", *paths)
    return members(data, mode)


def package(root: Path, mode: str, baseline: str, output: Path, expected: str) -> dict:
    manifest = preflight(root, mode, baseline)
    if manifest["commit"] != expected:
        raise DeployError("HEAD_CHANGED")
    current = source(root, manifest["commit"], mode)
    previous = source(root, manifest["baseline"], mode)
    manifest.update(
        protocol=1,
        version="1.3.6",
        files=fingerprints(current),
        baseline_files=fingerprints(previous),
    )
    # All source bytes/modes originate from git archive; only this non-secret
    # manifest is generated. No working-tree files or automatic .env inclusion.
    current["deployment.json"] = (json.dumps(manifest, sort_keys=True).encode(), 0o644)
    with (
        output.open("xb") as target,
        gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w|") as archive,
    ):
        for name, (data, permissions) in sorted(current.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = permissions
            archive.addfile(info, io.BytesIO(data))
    return {
        "commit": manifest["commit"],
        "short": manifest["commit"][:12],
        "filename": output.name,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "package"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=("web", "app"), required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve()
        result = preflight(root, args.mode, args.baseline)
        if args.action == "package":
            if not args.output or not args.expected_head:
                raise DeployError("INVALID_ARGUMENTS")
            result = package(root, args.mode, args.baseline, Path(args.output), args.expected_head)
        print(json.dumps(result))
        return 0
    except DeployError as exc:
        print(str(exc))
    except Exception:  # noqa: BLE001 -- boundary must redact all underlying error text
        print("PACKAGE_FAILED_SAFELY")
    return 1


if __name__ == "__main__":
    sys.exit(main())
