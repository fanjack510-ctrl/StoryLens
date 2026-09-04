"""Read-only R6 corrective acceptance gate; NOT an installed deployment tool.

Compare externally pinned archives before accepting root-retained R5 evidence.
Never reads env, Secret, Docker configuration or business data. No mutations.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path, PurePosixPath

R5 = "18f8ee3ea28ce5717481972c29ea04e8e0613702"
R5_SHA = "c9e1349c09cdcbd55a13267d4fdfb4f71db09c0a84564950c7778e3bc18908d1"
TV = "32799f5ea99f29821eb799dc03f439d09d5a58028f94e227e5b24190f0756dda"
TOOLS = (
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
SERVICES = {
    "online-web",
    "online-api",
    "online-worker",
    "postgres",
    "redis",
    "pocketbase",
    "pocketbase-init",
    "schema-init",
}
PROJECTS = {
    "sl-accept-webd20260904r5": ("web", "UPDATE_OK"),
    "sl-accept-webe20260904r5": ("web", "UPDATE_FAILED_ROLLBACK_OK"),
    "sl-accept-appf20260904r5": ("app", "UPDATE_OK"),
    "sl-accept-appg20260904r5": ("app", "UPDATE_FAILED_ROLLBACK_OK"),
}
NON_RUNTIME = {
    "bootstrap.json",
    "infra/online/ACCEPTANCE.md",
    "infra/online/R6-H-ONLY.md",
    "release/changes/CHG-20260903-001.json",
}


def require(condition):
    if not condition:
        raise ValueError("R6_GATE_FAILED_FULL_ACCEPTANCE_REQUIRED")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(path, expected_sha):
    require(sha(path.read_bytes()) == expected_sha)
    files = {}
    with tarfile.open(path, "r:gz") as tar:
        for item in tar:
            name = item.name
            require(item.isfile() and not item.issym() and not item.islnk())
            require(str(PurePosixPath(name)) == name and not name.startswith("/"))
            require(".." not in PurePosixPath(name).parts and "\\" not in name)
            require(name not in files and item.size <= 8_000_000)
            files[name] = (tar.extractfile(item).read(), item.mode)
    meta = json.loads(files["bootstrap.json"][0])
    require(set(meta["files"]) == set(files) - {"bootstrap.json"})
    require(all(sha(files[n][0]) == h for n, h in meta["files"].items()))
    digest = hashlib.sha256()
    for name in sorted(TOOLS):
        digest.update(name.encode() + b"\0" + files["infra/online/" + name][0] + b"\0")
    require(meta["protocol"] == 2 and meta["tool_version"] == digest.hexdigest() == TV)
    require(re.fullmatch("[a-f0-9]{40}", meta["commit"]))
    require(files["VERSION"][0].strip() == b"1.3.6")
    return files, meta


def equivalent(old, new):
    # Fail closed on EVERY unknown new/deleted/changed input, not just known files.
    protected = lambda n: n not in NON_RUNTIME and not n.startswith("infra/online/tests/")
    left = {n: v for n, v in old.items() if protected(n)}
    right = {n: v for n, v in new.items() if protected(n)}
    require(left == right)
    require(all("infra/online/" + n in left for n in TOOLS))
    return {n: sha(v[0]) for n, v in sorted(left.items())}


def private(path, directory=False):
    info = path.lstat()  # never follow links, including ancestor links
    require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode))
    require(info.st_uid == info.st_gid == 0)
    require(stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600))
    require(directory or info.st_nlink == 1)
    for parent in path.parents:
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == st.st_gid == 0)
        # Same kernel boundary as the unchanged installer: /run/lock may be
        # root-owned sticky 1777; our leaf must still be root-only 0700.
        shared_lock_parent = parent == Path("/run/lock") and stat.S_IMODE(st.st_mode) == 0o1777
        require(shared_lock_parent or not st.st_mode & 0o022)


def read_record(path):
    private(path)
    require(path.stat().st_size < 2_000_000)
    return json.loads(path.read_text())


def run(args):
    result = subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    require(result.returncode == 0)
    return result.stdout.strip()


def evidence(root, locks, baseline, call=run):
    private(locks, True)
    hashes = {}
    for project, (mode, expected) in PROJECTS.items():
        state, ev = root / project / "state", root / project / "evidence"
        private(state, True)
        private(ev, True)
        lock = locks / (project + ".lock")
        private(lock)
        info = lock.lstat()
        hashes[str(lock)] = sha(
            json.dumps(
                [
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_uid,
                    info.st_gid,
                    info.st_nlink,
                    info.st_size,
                    info.st_mtime_ns,
                ]
            ).encode()
        )
        require(not os.path.lexists(state / "pending.json"))
        session = read_record(state / "session.json")
        require(session["ready"] is True and session["project"] == project)
        require(session["mode"] == mode)
        require(
            session["baseline"]
            == {n: sha(v[0]) for n, v in baseline.items() if n != "bootstrap.json"}
        )
        candidate = dict(session["baseline"])
        changed = (
            "apps/online_web/index.html"
            if mode == "web"
            else "apps/online_api/storylens_online/errors.py"
        )
        content = baseline[changed][0]
        content = (
            content.replace(
                b"</head>", b'<meta name="storylens-acceptance" content="candidate-v2"></head>'
            )
            if mode == "web"
            else content
            + b"\n# Isolated deployment acceptance candidate v2; no business changes.\n"
        )
        candidate[changed] = sha(content)
        require(session["candidates"][mode] == candidate)
        records = []
        for path in sorted(ev.glob("*.json")):
            record = read_record(path)
            records.append(record)
            hashes[str(path)] = sha(path.read_bytes())
        hashes[str(state / "session.json")] = sha((state / "session.json").read_bytes())
        images = [r for r in records if r["status"] == "IMAGE_RUNTIME_CONTRACT_OK"]
        secrets = [r for r in records if r["status"] == "SECRET_BOUNDARY_OK"]
        updates = [r for r in records if r["status"] == expected]
        require(images and secrets and len(updates) == 1)
        require(
            all(
                r["status"] in {expected, "SECRET_BOUNDARY_OK", "IMAGE_RUNTIME_CONTRACT_OK"}
                for r in records
            )
        )
        require(all(r["mode"] == mode and r["project"] == project for r in secrets))
        manifests = [session["baseline"], session["candidates"][mode]]
        # Both baseline and App candidate probes must be retained, not merely a
        # single unrelated successful probe alongside the final update record.
        for manifest in manifests if mode == "app" else manifests[:1]:
            expected_files = {
                n.removeprefix("apps/online_api/storylens_online/"): h
                for n, h in manifest.items()
                if n.startswith("apps/online_api/storylens_online/")
            }
            require(any(image["files"] == expected_files for image in images))
        for image in images:
            require(re.fullmatch("sha256:[a-f0-9]{64}", image["image"]))
            require(
                any(
                    image["files"]
                    == {
                        n.removeprefix("apps/online_api/storylens_online/"): h
                        for n, h in m.items()
                        if n.startswith("apps/online_api/storylens_online/")
                    }
                    and image["entrypoint"] == m["infra/online/worker-entrypoint.sh"]
                    for m in manifests
                )
            )
            require(
                all(
                    "db/" + n in image["files"]
                    for n in ("init_schema.py", "models.py", "phase2b1_migration.py")
                )
            )
        update = updates[0]
        require(update["database_unchanged"] is True)
        require(update["mode"] == mode and update["project"] == project)
        require(set(update["before"]) == set(update["after"]) == SERVICES)
        targets = {"online-web"} if mode == "web" else {"online-api", "online-worker"}
        for name in SERVICES:
            before, after = update["before"][name], update["after"][name]
            require(re.fullmatch("[a-f0-9]{64}", after))
            require((before != after) == (name in targets))
            # Retained stopped resources must still exist under the original project.
            identity = call(
                [
                    "inspect",
                    "--format",
                    (
                        '{{index .Config.Labels "com.docker.compose.project"}} '
                        '{{index .Config.Labels "com.docker.compose.service"}}'
                    ),
                    after,
                ]
            )
            require(identity == project + " " + name)
    return hashes


def production(audit, call=run):
    private(audit, True)
    old = {}
    for name in ("images-before.txt", "volumes-before.txt"):
        path = audit / name
        private(path)
        old[name] = set(path.read_text().splitlines())
        require(old[name])
    ids = call(["ps", "-aq", "--filter", "label=com.docker.compose.project=storylens-online"])
    current = set()
    for identifier in ids.splitlines():
        require(re.fullmatch("[a-f0-9]{12,64}", identifier))
        current.add(
            call(["inspect", "--format", "{{.Id}} {{.Image}} {{.RestartCount}}", identifier])
        )
    require(current == old["images-before.txt"])
    volumes = call(
        [
            "volume",
            "ls",
            "--filter",
            "label=com.docker.compose.project=storylens-online",
            "--format",
            "{{.Name}}",
        ]
    )
    require(set(volumes.splitlines()) == old["volumes-before.txt"])
    # R5 A recorded names only. Reject replacement volumes created AFTER that
    # original root-owned snapshot, rather than claiming names prove identity.
    captured = (audit / "volumes-before.txt").stat().st_mtime
    for name in volumes.splitlines():
        require(re.fullmatch("storylens-online_[a-z_]+", name))
        created = call(["volume", "inspect", "--format", "{{.CreatedAt}}", name])
        date = datetime.fromisoformat(created.replace("Z", "+00:00"))  # noqa: FURB162 -- Python 3.10 server
        require(date.tzinfo is not None and date.timestamp() < captured)
    require(os.readlink("/opt/storylens/current") == "/opt/storylens/releases/4ae7f663")
    return {n: sorted(v) for n, v in old.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--r5-package", required=True, type=Path)
    parser.add_argument("--r6-package", required=True, type=Path)
    parser.add_argument("--r6-sha256", required=True)
    parser.add_argument("--r5-audit", type=Path)
    parser.add_argument("--artifacts-only", action="store_true")
    args = parser.parse_args()
    try:
        old, previous = archive(args.r5_package, R5_SHA)
        new, current = archive(args.r6_package, args.r6_sha256)
        require(previous["commit"] == R5 and current["commit"] != R5)
        inputs = equivalent(old, new)
        result = {
            "status": "RUNTIME_BUILD_EQUIVALENT",
            "r5": R5,
            "r6": current["commit"],
            "protocol": 2,
            "tool_version": TV,
            "files": inputs,
        }
        if not args.artifacts_only:
            require(os.name == "posix" and os.getuid() == 0 and args.r5_audit is not None)
            result["evidence"] = evidence(
                Path("/opt/storylens/acceptance"), Path("/run/lock/storylens-online-deploy"), old
            )
            result["production"] = production(args.r5_audit)
            result["status"] = "R5_DG_LINKABLE_H_STILL_REQUIRED"
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:  # noqa: BLE001 -- never expose raw audit/OS errors
        print("R6_GATE_FAILED_FULL_ACCEPTANCE_REQUIRED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
