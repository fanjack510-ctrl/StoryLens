"""Root-only deployment coordinator; no business or credential imports.

The shell uses isolated Python; helpers are imported only from its trusted
installation directory, never from a received release or an environment path.
"""

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_package import MAX_BYTES, fingerprints, members
from deploy_policy import BUILD, MODULE, SUPPORT, DeployError, require_mode

ALL_SERVICES = (
    "online-web",
    "online-api",
    "online-worker",
    "gateway",
    "postgres",
    "redis",
    "pocketbase",
    "pocketbase-init",
)
TARGETS = {"web": ("online-web",), "app": ("online-api", "online-worker")}
COMMANDS = {
    "online-api": [
        "uvicorn",
        "storylens_online.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
        "--no-server-header",
    ],
    "online-worker": ["python", "-m", "storylens_online.worker"],
}
LIVE_TAG = {"web": "storylens-online-web:lightweight", "app": "storylens-online-api:local"}
VOLUMES = (
    "caddy_data",
    "caddy_config",
    "pocketbase_data",
    "postgres_data",
    "redis_data",
    "online_uploads",
)


def run_command(args: list[str], timeout: int = 120) -> str:
    # Never stream Compose/build/curl/inspect output: it may contain credentials.
    try:
        # A Docker CLI may read stdin even with Compose exec -T. Never let it
        # consume the remaining program of an enclosing `ssh ... bash -s`.
        result = subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=timeout
        )
        if result.returncode:
            raise DeployError("COMMAND_FAILED_SAFELY")
        return result.stdout.decode("utf-8").strip()
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise DeployError("COMMAND_FAILED_SAFELY") from None


def validate_args(mode: str, commit: str, name: str, digest: str, baseline: str, domain: str):
    if (
        mode not in TARGETS
        or not re.fullmatch(r"[0-9a-f]{40}", commit)
        or not re.fullmatch(r"[0-9a-f]{40}", baseline)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or not re.fullmatch(r"storylens-deploy-[0-9a-f]{32}\.tar\.gz", name)
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", domain)
        or ".." in domain
        or "." not in domain
    ):
        raise DeployError("INVALID_ARGUMENTS")


def regular(path: Path) -> None:
    if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)):
        raise DeployError("UNSAFE_PATH")


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".new")
    with temporary.open("x", encoding="utf-8") as output:
        json.dump(data, output, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


class Deployment:
    def __init__(
        self,
        root=Path("/opt/storylens"),
        incoming=Path("/tmp"),
        runner=run_command,
        sleep=time.sleep,
    ):
        self.root, self.incoming, self.run, self.sleep = root, incoming, runner, sleep
        self.shared = root / "shared"
        self.override = self.shared / "lightweight-compose.json"
        self.pending = self.shared / "lightweight-pending.json"
        self.current = root / "current"

    def release_target(self, pointer: Path) -> Path:
        if not pointer.is_symlink():
            raise DeployError("UNSAFE_CURRENT_POINTER")
        target = pointer.resolve(strict=True)
        if target.parent != self.root / "releases" or not re.fullmatch(
            r"[0-9a-f]{8,40}", target.name
        ):
            raise DeployError("UNSAFE_CURRENT_POINTER")
        return target

    def compose(self, *args: str) -> str:
        command = [
            "docker",
            "compose",
            "--project-name",
            "storylens-online",
            "--project-directory",
            str(self.stable / "infra/online"),
            "--env-file",
            str(self.shared / "online.env"),
            "-f",
            str(self.stable / "infra/online/docker-compose.yml"),
        ]
        if self.override.exists():
            regular(self.override)
            command += ["-f", str(self.override)]
        return self.run([*command, *args])

    def ids(self) -> dict:
        result = {}
        for service in ALL_SERVICES:
            value = self.compose("ps", "-aq", service)
            if not re.fullmatch(r"[0-9a-f]{12,64}", value):
                raise DeployError("SERVICE_SET_MISMATCH")
            result[service] = value
        return result

    def inspect(self, identifier: str, field: str) -> str:
        # Only these individual non-secret fields, never complete inspect JSON.
        if field not in {".Image", ".State", ".RestartCount"}:
            raise DeployError("INVALID_INSPECT_FIELD")
        return self.run(["docker", "inspect", "--format", "{{json " + field + "}}", identifier])

    def volume_identity(self) -> dict:
        # Inspect fixed names only, never create a missing volume or read data.
        return {
            name: self.run(
                [
                    "docker",
                    "volume",
                    "inspect",
                    "--format",
                    "{{json .CreatedAt}}",
                    f"storylens-online_{name}",
                ]
            )
            for name in VOLUMES
        }

    def healthy(self, mode: str, domain: str) -> None:
        for _ in range(45):
            values = self.ids()
            good = True
            for service in TARGETS[mode]:
                state = json.loads(self.inspect(values[service], ".State"))
                if int(self.inspect(values[service], ".RestartCount")) != 0:
                    raise DeployError("CONTAINER_RESTARTED")
                good &= state.get("Status") == "running"
                if service != "online-worker":
                    good &= state.get("Health", {}).get("Status") == "healthy"
            if good:
                break
            self.sleep(2)
        else:
            raise DeployError("HEALTH_CHECK_FAILED")
        # Observe beyond an immediate running state, including Worker startup.
        self.sleep(6)
        for service in TARGETS[mode]:
            state = json.loads(self.inspect(values[service], ".State"))
            if state.get("Status") != "running" or int(
                self.inspect(values[service], ".RestartCount")
            ):
                raise DeployError("HEALTH_CHECK_FAILED")
            if service != "online-worker" and state.get("Health", {}).get("Status") != "healthy":
                raise DeployError("HEALTH_CHECK_FAILED")
        status = self.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--noproxy",
                "*",
                "--max-time",
                "15",
                "--resolve",
                f"{domain}:443:127.0.0.1",
                "--output",
                "/dev/null",
                "--write-out",
                "%{http_code}",
                f"https://{domain}/",
            ]
        )
        if status != "200":
            raise DeployError("ROOT_HEALTH_FAILED")

    def unchanged(self, before: dict, mode: str) -> None:
        after = self.ids()
        if any(after[name] != value for name, value in before.items() if name not in TARGETS[mode]):
            raise DeployError("UNRELATED_CONTAINER_CHANGED")
        if self.release_target(self.current) != self.stable:
            raise DeployError("CURRENT_CHANGED")
        if self.volume_identity() != self.before_volumes:
            raise DeployError("VOLUME_CHANGED")

    def read_override(self) -> dict:
        if not self.override.exists() and not self.override.is_symlink():
            return {"services": {}}
        regular(self.override)
        value = json.loads(self.override.read_text())
        if set(value) != {"services"} or not isinstance(value["services"], dict):
            raise DeployError("INVALID_RUNTIME_OVERRIDE")
        for name, config in value["services"].items():
            mode = "web" if name == "online-web" else "app"
            expected = {"image": LIVE_TAG[mode]}
            if name in COMMANDS:
                expected["command"] = COMMANDS[name]
            if name not in (*TARGETS["web"], *TARGETS["app"]) or config != expected:
                raise DeployError("INVALID_RUNTIME_OVERRIDE")
        return value

    def verify_bundle(self, mode: str, commit: str, name: str, digest: str, baseline: str):
        package_path = self.incoming / name
        regular(package_path)
        fd = os.open(package_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise DeployError("INVALID_ARCHIVE")
            raw = stream.read(MAX_BYTES + 1)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise DeployError("SHA256_MISMATCH")
        content = members(raw, mode)
        manifest = json.loads(content.pop("deployment.json")[0])
        if any(
            manifest.get(key) != value
            for key, value in {
                "protocol": 1,
                "commit": commit,
                "baseline": baseline,
                "mode": mode,
                "version": "1.3.6",
            }.items()
        ):
            raise DeployError("MANIFEST_MISMATCH")
        require_mode(manifest["changed"], mode)
        if manifest["files"] != fingerprints(content):
            raise DeployError("MANIFEST_MISMATCH")
        pointer = self.root / f"current-{mode}"
        if pointer.exists() or pointer.is_symlink():
            previous = self.release_target(pointer)
            regular(previous / "deployment.json")
            if json.loads((previous / "deployment.json").read_text())["commit"] != previous.name:
                raise DeployError("BASELINE_MISMATCH")
        else:
            previous = self.stable
        # Recompute the deployed source manifest, not a user-supplied diff alone.
        # A later baseline may be source-equivalent for this component (e.g. an
        # already deployed App commit after the last Web commit). Matching ALL
        # component/support hashes permits alternating deploys without treating
        # already deployed changes as pending. It never permits source drift.
        previous_files = {}
        paths = list((previous / MODULE[mode]).rglob("*"))
        paths += [previous / path for path in (*SUPPORT, *BUILD[mode])]
        for path in paths:
            if path.is_symlink():
                raise DeployError("UNSAFE_PATH")
            if path.is_file():
                previous_files[path.relative_to(previous).as_posix()] = (
                    path.read_bytes(),
                    0o755 if path.stat().st_mode & 0o111 else 0o644,
                )
        if fingerprints(previous_files) != manifest["baseline_files"]:
            raise DeployError("DEPLOYED_SOURCE_DRIFT")
        if set(SUPPORT) - set(content) or set(BUILD[mode]) - set(content):
            raise DeployError("INCOMPLETE_ARCHIVE")
        for path in SUPPORT:
            regular(self.stable / path)
            if content[path][0] != (self.stable / path).read_bytes():
                raise DeployError("FULL_DEPLOYMENT_REQUIRED")
        new_hashes, old_hashes = fingerprints(content), fingerprints(previous_files)
        actual = [
            path
            for path in set(content) | set(previous_files)
            if new_hashes.get(path) != old_hashes.get(path)
        ]
        require_mode(actual, mode)
        return content, manifest, pointer

    def update_pointer(self, pointer: Path, release: Path) -> None:
        temporary = self.root / (pointer.name + ".new")
        os.symlink(release, temporary, target_is_directory=True)
        try:
            os.replace(temporary, pointer)
        finally:
            if temporary.is_symlink():
                temporary.unlink()

    def deploy(self, mode: str, commit: str, name: str, digest: str, baseline: str, domain: str):
        validate_args(mode, commit, name, digest, baseline, domain)
        self.stable = self.release_target(self.current)
        for directory in (self.root, self.root / "releases", self.shared):
            if directory.is_symlink() or not directory.is_dir():
                raise DeployError("UNSAFE_PATH")
        if self.pending.exists() or self.pending.is_symlink():
            raise DeployError("MANUAL_RECOVERY_REQUIRED")
        regular(self.shared / "online.env")  # Check only; never read its contents.
        regular(self.stable / "infra/online/docker-compose.yml")
        release = self.root / "releases" / commit
        if release.exists() or release.is_symlink():
            raise DeployError("RELEASE_ALREADY_EXISTS")
        content, manifest, pointer = self.verify_bundle(mode, commit, name, digest, baseline)
        old_pointer = self.release_target(pointer) if pointer.is_symlink() else None
        runtime = self.read_override()
        before = self.ids()
        self.before_volumes = self.volume_identity()
        self.healthy(mode, domain)  # Refuse to deploy into an already unhealthy target.
        images = {json.loads(self.inspect(before[s], ".Image")) for s in TARGETS[mode]}
        if len(images) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", next(iter(images))):
            raise DeployError("IMAGE_BASELINE_MISMATCH")
        old_image = next(iter(images))
        rollback = f"storylens-online-{mode}:rollback-{commit}"
        candidate = f"storylens-online-{mode}:commit-{commit}"
        release.mkdir(mode=0o755)
        for path, (data, permissions) in content.items():
            destination = release / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            for parent in destination.parents:
                if parent == release:
                    break
                parent.chmod(0o755)
            with destination.open("xb") as output:
                output.write(data)
            destination.chmod(permissions)
        atomic_json(release / "deployment.json", manifest)
        self.run(
            [
                "docker",
                "build",
                "--tag",
                candidate,
                "--file",
                str(release / BUILD[mode][0]),
                str(release),
            ],
            timeout=1800,
        )
        self.run(["docker", "image", "tag", old_image, rollback])
        for service in TARGETS[mode]:
            runtime["services"][service] = {"image": LIVE_TAG[mode]}
            if service in COMMANDS:
                runtime["services"][service]["command"] = COMMANDS[service]
        # Pin image selection and no-migration commands even on rollback. Existing
        # settings for the other component are preserved unchanged.
        atomic_json(self.pending, {"mode": mode, "commit": commit, "rollback": rollback})
        try:
            atomic_json(self.override, runtime)
            self.run(["docker", "image", "tag", candidate, LIVE_TAG[mode]])
            self.compose("up", "-d", "--no-build", "--no-deps", *TARGETS[mode])
            self.healthy(mode, domain)
            self.unchanged(before, mode)
            self.update_pointer(pointer, release)
        except BaseException:  # noqa: BLE001 -- rollback also on interrupts, never echo raw errors
            try:
                self.run(["docker", "image", "tag", rollback, LIVE_TAG[mode]])
                atomic_json(self.override, runtime)
                self.compose("up", "-d", "--no-build", "--no-deps", *TARGETS[mode])
                self.healthy(mode, domain)
                self.unchanged(before, mode)
                if pointer.is_symlink() and self.release_target(pointer) == release:
                    if old_pointer is None:
                        pointer.unlink()
                    else:
                        self.update_pointer(pointer, old_pointer)
                self.pending.unlink()
            except BaseException:  # noqa: BLE001 -- preserve recovery marker and redact
                raise DeployError("ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED") from None
            raise DeployError("DEPLOY_FAILED_ROLLED_BACK") from None
        self.pending.unlink()
        return "DEPLOY_SUCCEEDED"


def main() -> int:
    # fcntl exists on the target Linux host, not on the Windows test runner.
    import fcntl

    def interrupted(*_):
        raise DeployError("DEPLOY_INTERRUPTED")

    try:
        if len(sys.argv) != 7 or os.geteuid() != 0:
            raise DeployError("INVALID_ARGUMENTS")
        validate_args(*sys.argv[1:])
        os.umask(0o077)
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        lock = Path("/opt/storylens/shared/lightweight-deploy.lock")
        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(Deployment().deploy(*sys.argv[1:]))
        return 0
    except DeployError as exc:
        print(str(exc))
    except BaseException:  # noqa: BLE001 -- privileged CLI error redaction boundary
        print("DEPLOY_FAILED_SAFELY")
    return 1


if __name__ == "__main__":
    sys.exit(main())
