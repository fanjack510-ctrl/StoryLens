"""Reproducible full online bootstrap from committed Git source, not local state."""

import argparse
import gzip
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_package import MAX_BYTES, git
from deploy_policy import DeployError, scan_secret, valid_path
from deploy_protocol import PROTOCOL, TOOL_FILES


def make_bootstrap(root: Path, output_dir: Path) -> dict:
    if git(root, "status", "--porcelain").strip():
        raise DeployError("WORKTREE_NOT_CLEAN")
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    paths = (
        git(root, "ls-files", "apps/online_api", "apps/online_web", "infra/online")
        .decode()
        .splitlines()
    )
    paths = [
        p
        for p in paths
        if (Path(p).name == ".env.example" or not Path(p).name.startswith((".env", ".git")))
    ]
    paths += ["VERSION", "scripts/deploy_online.ps1", "release/changes/CHG-20260903-001.json"]
    raw = git(root, "archive", "--format=tar", commit, "--", *paths)
    data = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for item in archive:
            if item.isdir():
                continue
            if not item.isfile() or not valid_path(item.name):
                raise DeployError("INVALID_ARCHIVE")
            value = archive.extractfile(item).read()
            scan_secret(value)
            data[item.name] = (value, 0o755 if item.mode & 0o111 else 0o644)
    if data["VERSION"][0].strip() != b"1.3.6":
        raise DeployError("VERSION_MISMATCH")
    digest = hashlib.sha256()
    for name in sorted(TOOL_FILES):
        digest.update(name.encode() + b"\0" + data["infra/online/" + name][0] + b"\0")
    manifest = {
        "commit": commit,
        "protocol": PROTOCOL,
        "tool_version": digest.hexdigest(),
        "version": "1.3.6",
        "change_id": "CHG-20260903-001",
        "files": {n: hashlib.sha256(v[0]).hexdigest() for n, v in sorted(data.items())},
    }
    data["bootstrap.json"] = (json.dumps(manifest, indent=2).encode(), 0o644)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"storylens-online-lightweight-bootstrap-{commit[:8]}.tar.gz"
    with (
        output.open("xb") as target,
        gzip.GzipFile(fileobj=target, mode="wb", mtime=0, filename="") as zipped,
        tarfile.open(fileobj=zipped, mode="w|") as archive,
    ):
        for name, (value, mode) in sorted(data.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(value), mode
            archive.addfile(item, io.BytesIO(value))
    if output.stat().st_size > MAX_BYTES:
        raise DeployError("PACKAGE_TOO_LARGE")
    return {
        "path": str(output),
        "size": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "entries": len(data),
        "commit": commit,
        "tool_version": manifest["tool_version"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(make_bootstrap(args.root, args.output_dir), indent=2))
