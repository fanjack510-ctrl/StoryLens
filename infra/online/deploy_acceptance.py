"""Isolated real-Docker acceptance. No production configuration or secrets imported."""

import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path

from deploy_image_contract import context_contract, copy_context, verify_image
from deploy_install import verify_source
from deploy_policy import DeployError, require_mode
from deploy_protocol import trusted
from deploy_runtime import COMMANDS, TARGETS, run_command

ACCEPTANCE_ROOT = Path("/opt/storylens/acceptance")
SERVICES = (
    "online-web",
    "online-api",
    "online-worker",
    "postgres",
    "redis",
    "pocketbase",
    "pocketbase-init",
    "schema-init",
)
TEST_KEY = b"sk-" + b"STORYLENS_ACCEPTANCE_ONLY_" + b"NOT_A_REAL_KEY"

# These exact scripts are exercised by subprocess permission tests on Linux.
# No secret bytes, digests or exception text are returned to the operator.
WORKER_IDENTITY_PROBE = """
import os, pathlib
assert os.geteuid() == os.getegid() == 10001
s = pathlib.Path('/proc/1/status').read_text()
assert 'Uid:\\t10001\\t10001\\t10001\\t10001' in s
assert 'Gid:\\t10001\\t10001\\t10001\\t10001' in s
"""
WEB_SECRET_ROOT_PROBE = """
import os, stat
assert os.geteuid() == os.getegid() == 0
d = os.lstat('/run/storylens-online')
assert stat.S_ISDIR(d.st_mode) and stat.S_IMODE(d.st_mode) == 0o700
assert d.st_uid == d.st_gid == 0
try:
    os.lstat('/run/storylens-online/deepseek-api-key')
except FileNotFoundError:
    pass
else:
    raise AssertionError
"""
APP_SECRET_USER_PROBE = """
import os
p = '/run/storylens-online/deepseek-api-key'
fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
os.close(fd)
try:
    fd = os.open('/run/secrets/storylens_online_deepseek_api_key', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
except PermissionError:
    pass
else:
    os.close(fd)
    raise AssertionError
"""
APP_SECRET_ROOT_PROBE = """
import os, stat
assert os.geteuid() == os.getegid() == 0
d = os.lstat('/run/storylens-online')
assert stat.S_ISDIR(d.st_mode) and stat.S_IMODE(d.st_mode) == 0o700
assert d.st_uid == d.st_gid == 10001
values = []
for path, uid, mode in (
    ('/run/secrets/storylens_online_deepseek_api_key', 0, 0o600),
    ('/run/storylens-online/deepseek-api-key', 10001, 0o400),
):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1
        assert stat.S_IMODE(s.st_mode) == mode and s.st_uid == s.st_gid == uid
        value = os.read(fd, 4097)
        assert 0 < len(value) <= 4096 and not os.read(fd, 1)
        values.append(value)
    finally:
        os.close(fd)
assert values[0] == values[1]
"""


def local_docker(args, timeout=120):
    if not args or args[0] != "docker":
        raise DeployError("INVALID_ACCEPTANCE_COMMAND")
    return run_command(["docker", "--host", "unix:///var/run/docker.sock", *args[1:]], timeout)


def project_name(value: str) -> None:
    if not re.fullmatch(r"sl-accept-[a-z0-9]{8,24}", value):
        raise DeployError("INVALID_ACCEPTANCE_PROJECT")


def create_test_key(project: str, dry_run: bool):
    project_name(project)
    directory = Path("/opt/storylens/acceptance-input") / project
    for item in (directory, *directory.parents):
        if item.exists() or item.is_symlink():
            trusted(item)
    path = directory / "deepseek-test-key"
    if path.exists() or path.is_symlink():
        raise DeployError("TEST_SECRET_ALREADY_EXISTS")
    if not dry_run:
        directory.mkdir(parents=True, mode=0o700)
        with path.open("xb") as stream:
            stream.write(TEST_KEY)
        path.chmod(0o600)
    return "DRY_RUN_OK" if dry_run else "FAKE_TEST_SECRET_CREATED"


def paths(project: str, state: Path, evidence: Path, candidate: Path | None = None) -> Path:
    project_name(project)
    root = ACCEPTANCE_ROOT / project
    if state != root / "state" or evidence != root / "evidence":
        raise DeployError("INVALID_ACCEPTANCE_PATH")
    if candidate is not None and candidate not in (
        root / "candidates/web",
        root / "candidates/app",
    ):
        raise DeployError("INVALID_CANDIDATE_PATH")
    for path in (root, state, evidence, candidate):
        if path is not None:
            for part in (path, *path.parents):
                if part.exists() or part.is_symlink():
                    trusted(part)
    return root


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".new")
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def tree_hashes(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        trusted(path)
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def health(command: list[str]) -> dict:
    return {"test": ["CMD", *command], "interval": "2s", "timeout": "5s", "retries": 30}


def compose_spec(project: str, state: Path, mode: str) -> dict:
    """Closed configuration, no extends/include/env_file/build/bind/socket/user inputs."""
    app_env = {
        "STORYLENS_ONLINE_DATABASE_URL": "postgresql+psycopg://storylens@postgres:5432/storylens_online",
        "STORYLENS_ONLINE_REDIS_URL": "redis://redis:6379/0",
        "STORYLENS_ONLINE_POCKETBASE_URL": "http://pocketbase:8090",
        "STORYLENS_ONLINE_FRONTEND_ORIGIN": "https://acceptance.invalid",
        "STORYLENS_ONLINE_PHASE2B1_ENABLED": "false",
        "STORYLENS_ONLINE_PHASE2B1_ALLOWLISTED_USER_IDS_CSV": "",
    }
    app = {
        "image": f"{project}-app:baseline",
        "environment": app_env,
        "command": COMMANDS["online-api"],
        "volumes": ["uploads:/srv/storylens-online/uploads"],
        "healthcheck": health(
            [
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live',timeout=3).read()",
            ]
        ),
    }
    worker = copy.deepcopy(app)
    worker.pop("healthcheck")
    worker.update(
        user="0:0",
        entrypoint=["/usr/local/bin/storylens-online-worker-entrypoint"],
        command=COMMANDS["online-worker"],
        tmpfs=["/run/storylens-online:rw,noexec,nosuid,nodev,size=64k,mode=0700"],
    )
    if mode == "app":
        worker["environment"] = {
            **app_env,
            "STORYLENS_ONLINE_PHASE2B1_ENABLED": "true",
            "STORYLENS_ONLINE_PHASE2B1_BASE_URL": "https://api.deepseek.com",
            "STORYLENS_ONLINE_PHASE2B1_API_KEY_FILE": "/run/storylens-online/deepseek-api-key",
        }
        worker["secrets"] = [
            {"source": "test_provider", "target": "storylens_online_deepseek_api_key"}
        ]
    pb = {
        "image": f"{project}-pocketbase:baseline",
        "volumes": ["pocketbase:/pb/pb_data"],
        "healthcheck": health(
            ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8090/api/health"]
        ),
    }
    pb_init = {
        "image": pb["image"],
        "volumes": pb["volumes"],
        "user": "0:0",
        "entrypoint": ["/bin/sh", "/pb/init-superuser.sh"],
        "command": [],
        "secrets": ["pocketbase_superuser_email", "pocketbase_superuser_password"],
    }
    schema = copy.deepcopy(app)
    schema.pop("healthcheck")
    schema["command"] = ["python", "-m", "storylens_online.db.init_schema"]
    services = {
        "online-web": {
            "image": f"{project}-web:baseline",
            "healthcheck": health(["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]),
        },
        "online-api": app,
        "online-worker": worker,
        "schema-init": schema,
        "postgres": {
            "image": "postgres:16-alpine",
            "environment": {
                "POSTGRES_USER": "storylens",
                "POSTGRES_DB": "storylens_online",
                "POSTGRES_HOST_AUTH_METHOD": "trust",
            },
            "volumes": ["postgres:/var/lib/postgresql/data"],
            "healthcheck": health(["pg_isready", "-U", "storylens", "-d", "storylens_online"]),
        },
        "redis": {
            "image": "redis:7-alpine",
            "volumes": ["redis:/data"],
            "healthcheck": health(["redis-cli", "ping"]),
        },
        "pocketbase": pb,
        "pocketbase-init": pb_init,
    }
    for service in services.values():
        service.update(networks=["isolated"], restart="no")
    secrets = {
        name: {"file": str(state / name)}
        for name in ("pocketbase_superuser_email", "pocketbase_superuser_password")
    }
    if mode == "app":
        secrets["test_provider"] = {"file": str(state / "test_provider")}
    return {
        "name": project,
        "services": services,
        "networks": {"isolated": {"internal": True}},
        "volumes": {n: {} for n in ("uploads", "postgres", "redis", "pocketbase")},
        "secrets": secrets,
    }


class Acceptance:
    def __init__(
        self,
        project: str,
        state: Path,
        evidence: Path,
        mode: str,
        runner=local_docker,
        sleep=time.sleep,
    ):
        if mode not in TARGETS:
            raise DeployError("INVALID_ARGUMENTS")
        self.root = paths(project, state, evidence)
        self.project, self.state, self.evidence, self.mode = project, state, evidence, mode
        self.run, self.sleep = runner, sleep

    def compose(self, *args):
        return self.run(
            [
                "docker",
                "compose",
                "--project-name",
                self.project,
                "--project-directory",
                str(self.state),
                "-f",
                str(self.state / "compose.json"),
                *args,
            ],
            timeout=1800,
        )

    def prepare(self, source: Path, test_secret: Path | None, dry_run: bool):
        meta = verify_source(source)
        if self.root.exists():
            raise DeployError("ACCEPTANCE_ALREADY_EXISTS")
        if self.mode == "app":
            if test_secret is None:
                raise DeployError("TEST_SECRET_REQUIRED")
            if (
                test_secret
                != Path("/opt/storylens/acceptance-input") / self.project / "deepseek-test-key"
            ):
                raise DeployError("INVALID_TEST_SECRET_PATH")
            trusted(test_secret)
            if (
                not test_secret.is_file()
                or test_secret.stat().st_nlink != 1
                or test_secret.stat().st_size != len(TEST_KEY)
                or test_secret.stat().st_mode & 0o777 != 0o600
                or test_secret.read_bytes() != TEST_KEY
            ):
                raise DeployError("ONLY_FIXED_FAKE_SECRET_ALLOWED")
        elif test_secret is not None:
            raise DeployError("WEB_SECRET_FORBIDDEN")
        # Refuse *any* preexisting project/container/volume/network before allocating.
        for kind in ("container", "volume", "network"):
            if self.run(
                [
                    "docker",
                    kind,
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={self.project}",
                ]
            ):
                raise DeployError("ACCEPTANCE_PROJECT_EXISTS")
        for name in ("uploads", "postgres", "redis", "pocketbase"):
            if self.run(
                ["docker", "volume", "ls", "-q", "--filter", f"name=^{self.project}_{name}$"]
            ):
                raise DeployError("ACCEPTANCE_VOLUME_EXISTS")
        if self.run(
            ["docker", "network", "ls", "-q", "--filter", f"name=^{self.project}_isolated$"]
        ):
            raise DeployError("ACCEPTANCE_NETWORK_EXISTS")
        if dry_run:
            return "DRY_RUN_OK"
        production = self.production_snapshot()
        self.state.mkdir(parents=True, mode=0o700)
        self.evidence.mkdir(mode=0o700)
        baseline = self.root / "baseline"
        write_json(
            self.state / "session.json",
            {
                "project": self.project,
                "mode": self.mode,
                "ready": False,
                "phase": "source_preparation",
            },
        )
        try:
            copy_context(source, baseline, meta["files"])
        except Exception:  # noqa: BLE001 -- preserve a fixed failure checkpoint
            write_json(
                self.evidence / "source-preparation-failed.json",
                {
                    "status": "BUILD_CONTEXT_CONTRACT_FAILED",
                    "project": self.project,
                },
            )
            raise DeployError("BUILD_CONTEXT_CONTRACT_FAILED") from None
        hashes = tree_hashes(baseline)
        for mode in TARGETS:
            candidate = self.root / "candidates" / mode
            copy_context(baseline, candidate, hashes)
            changed = candidate / (
                "apps/online_web/index.html"
                if mode == "web"
                else "apps/online_api/storylens_online/errors.py"
            )
            value = changed.read_bytes()
            if mode == "web":
                value = value.replace(
                    b"</head>", b'<meta name="storylens-acceptance" content="candidate-v2"></head>'
                )
            else:
                value += b"\n# Isolated deployment acceptance candidate v2; no business changes.\n"
            changed.chmod(0o600)
            changed.write_bytes(value)
            changed.chmod(0o444)
        # Public fake PB credentials: never production identities, private network only.
        for name, value in {
            "pocketbase_superuser_email": b"acceptance@example.invalid",
            "pocketbase_superuser_password": b"acceptance-only-not-production-password",
        }.items():
            (self.state / name).write_bytes(value)
            (self.state / name).chmod(0o600)
        if test_secret:
            (self.state / "test_provider").write_bytes(TEST_KEY)
            (self.state / "test_provider").chmod(0o600)
        spec = compose_spec(self.project, self.state, self.mode)
        write_json(self.state / "compose.json", spec)
        record = {
            "mode": self.mode,
            "project": self.project,
            "baseline": hashes,
            "candidates": {m: tree_hashes(self.root / "candidates" / m) for m in TARGETS},
            "spec": spec,
            "ready": False,
        }
        write_json(self.state / "session.json", record)
        baseline_images = {}
        for mode in ("web", "app"):
            baseline_images[mode] = self.build(
                baseline, mode, f"{self.project}-{mode}:baseline", hashes
            )
        print("IMAGE_RUNTIME_CONTRACT_OK")
        for name in ("online-api", "online-worker", "schema-init"):
            spec["services"][name]["image"] = baseline_images["app"]
        spec["services"]["online-web"]["image"] = baseline_images["web"]
        record["baseline_images"] = baseline_images
        record["spec"] = spec
        write_json(self.state / "session.json", record)
        write_json(self.state / "compose.json", spec)
        self.run(
            [
                "docker",
                "build",
                "-t",
                f"{self.project}-pocketbase:baseline",
                str(baseline / "infra/online/pocketbase"),
            ],
            timeout=1800,
        )
        self.compose("up", "-d", "--no-build", "postgres", "redis")
        self.wait(("postgres", "redis"))
        self.compose(
            "up",
            "--no-build",
            "--abort-on-container-exit",
            "--exit-code-from",
            "pocketbase-init",
            "pocketbase-init",
        )
        self.compose("up", "-d", "--no-build", "pocketbase")
        self.wait(("pocketbase",))
        self.compose(
            "up",
            "--no-build",
            "--abort-on-container-exit",
            "--exit-code-from",
            "schema-init",
            "schema-init",
        )
        self.compose("up", "-d", "--no-build", "online-web", "online-api", "online-worker")
        self.wait(TARGETS["web"] + TARGETS["app"])
        self.audit_containers()
        self.secret_boundary()
        if production != self.production_snapshot():
            raise DeployError("PRODUCTION_CHANGED")
        record["ready"] = True
        write_json(self.state / "session.json", record)
        return "ACCEPTANCE_BASELINE_READY"

    def build(self, source: Path, mode: str, tag: str, manifest: dict):
        try:
            expected = context_contract(source, manifest)
            if self.run(["docker", "image", "ls", "-q", "--filter", f"reference={tag}"]):
                raise DeployError("ACCEPTANCE_IMAGE_ALREADY_EXISTS")
            self.run(
                [
                    "docker",
                    "build",
                    "--no-cache",
                    "--tag",
                    tag,
                    "--file",
                    str(source / f"infra/online/Dockerfile.{'web' if mode == 'web' else 'api'}"),
                    str(source),
                ],
                timeout=1800,
            )
            image = self.run(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
                raise DeployError("IMAGE_RUNTIME_CONTRACT_FAILED")
            if mode == "app":
                evidence = verify_image(self.run, image, expected)
                write_json(self.evidence / f"image-contract-{time.time_ns()}.json", evidence)
            return image
        except DeployError as exc:
            # Retain failed session/artifacts, never start services or erase evidence.
            code = (
                str(exc)
                if str(exc)
                in {
                    "BUILD_CONTEXT_CONTRACT_FAILED",
                    "IMAGE_RUNTIME_CONTRACT_FAILED",
                    "ACCEPTANCE_IMAGE_ALREADY_EXISTS",
                }
                else "IMAGE_BUILD_FAILED_SAFELY"
            )
            write_json(
                self.evidence / f"image-contract-failed-{time.time_ns()}.json",
                {
                    "status": code,
                    "mode": mode,
                    "project": self.project,
                },
            )
            raise DeployError(code) from None

    def ids(self):
        result = {}
        for service in SERVICES:
            value = self.compose("ps", "-aq", service)
            if not re.fullmatch(r"[a-f0-9]{12,64}", value):
                raise DeployError("ACCEPTANCE_SERVICE_MISSING")
            result[service] = value
        return result

    def inspect(self, identifier):
        value = json.loads(self.run(["docker", "inspect", identifier]))[0]
        if value["Config"]["Labels"].get("com.docker.compose.project") != self.project:
            raise DeployError("FOREIGN_CONTAINER")
        return value

    def audit_containers(self):
        for name, identifier in self.ids().items():
            info = self.inspect(identifier)
            host = info["HostConfig"]
            if (
                host.get("Privileged")
                or host.get("PortBindings")
                or host.get("NetworkMode") in {"host", "container"}
            ):
                raise DeployError("ISOLATION_FAILED")
            if set(info["NetworkSettings"]["Networks"]) != {self.project + "_isolated"}:
                raise DeployError("ISOLATION_FAILED")
            for mount in info["Mounts"]:
                if mount["Type"] == "volume":
                    if mount["Name"] not in {
                        self.project + "_" + n
                        for n in ("uploads", "postgres", "redis", "pocketbase")
                    }:
                        raise DeployError("FOREIGN_VOLUME")
                elif mount["Type"] == "bind":
                    allowed = (
                        {
                            str(self.state / n)
                            for n in ("pocketbase_superuser_email", "pocketbase_superuser_password")
                        }
                        if name == "pocketbase-init"
                        else {str(self.state / "test_provider")}
                        if name == "online-worker" and self.mode == "app"
                        else set()
                    )
                    if mount["Source"] not in allowed or mount["RW"]:
                        raise DeployError("FOREIGN_MOUNT")
                elif mount["Type"] != "tmpfs" or name != "online-worker":
                    raise DeployError("FOREIGN_MOUNT")
        net = json.loads(self.run(["docker", "network", "inspect", self.project + "_isolated"]))[0]
        if not net["Internal"] or net["Labels"].get("com.docker.compose.project") != self.project:
            raise DeployError("ISOLATION_FAILED")
        if not set(net["Containers"]) <= set(self.ids().values()):
            raise DeployError("FOREIGN_NETWORK_MEMBER")

    def wait(self, services):
        consecutive = 0
        for _ in range(60):
            good = True
            for name in services:
                identifier = self.compose("ps", "-aq", name)
                if not re.fullmatch(r"[a-f0-9]{12,64}", identifier):
                    good = False
                    continue
                info = self.inspect(identifier)
                good &= info["State"]["Status"] == "running" and info["RestartCount"] == 0
                if name != "online-worker":
                    good &= info["State"].get("Health", {}).get("Status") == "healthy"
            if good:
                consecutive += 1
                if consecutive >= 3:
                    return
            else:
                consecutive = 0
            self.sleep(2)
        raise DeployError("HEALTH_CHECK_FAILED")

    def database_fingerprint(self):
        schema = self.compose(
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            "storylens",
            "-d",
            "storylens_online",
            "--schema-only",
            "--no-owner",
        )
        # pg_dump adds a per-invocation restrict token on newer patch releases.
        schema = "\n".join(
            line
            for line in schema.splitlines()
            if not line.startswith(("\\restrict", "\\unrestrict"))
        )
        counts = self.compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "storylens",
            "-d",
            "storylens_online",
            "-At",
            "-c",
            "SELECT (SELECT count(*) FROM online_analysis_jobs),(SELECT count(*) FROM online_uploads),(SELECT count(*) FROM online_model_usage_ledger)",
        )
        return hashlib.sha256((schema + counts).encode()).hexdigest()

    def secret_boundary(self, *, record_evidence=True):
        try:
            self._secret_boundary()
            if record_evidence:
                write_json(
                    self.evidence / f"secret-boundary-{time.time_ns()}.json",
                    {"status": "SECRET_BOUNDARY_OK", "mode": self.mode, "project": self.project},
                )
        except BaseException:  # noqa: BLE001 -- fixed evidence, never native output
            if not record_evidence:  # a DryRun must remain read-only, even on failure
                raise DeployError("SECRET_BOUNDARY_FAILED") from None
            try:
                write_json(
                    self.evidence / f"secret-boundary-failed-{time.time_ns()}.json",
                    {
                        "status": "SECRET_BOUNDARY_FAILED",
                        "mode": self.mode,
                        "project": self.project,
                    },
                )
            except BaseException:  # noqa: BLE001 -- evidence storage can itself fail
                raise DeployError("SECRET_BOUNDARY_EVIDENCE_FAILED") from None
            raise DeployError("SECRET_BOUNDARY_FAILED") from None

    def _secret_boundary(self):
        info = self.inspect(self.ids()["online-worker"])
        flags = info["HostConfig"].get("Tmpfs", {}).get("/run/storylens-online", "")
        if not all(
            flag in flags.split(",")
            for flag in ("rw", "noexec", "nosuid", "nodev", "size=64k", "mode=0700")
        ):
            raise DeployError("WORKER_TMPFS_INVALID")
        binds = [m for m in info["Mounts"] if m["Type"] == "bind"]
        if self.mode == "app":
            if len(binds) != 1 or (
                binds[0]["Source"] != str(self.state / "test_provider")
                or binds[0]["Destination"] != "/run/secrets/storylens_online_deepseek_api_key"
                or binds[0]["RW"]
            ):
                raise DeployError("WORKER_SECRET_MOUNT_INVALID")
        elif binds:
            raise DeployError("WORKER_SECRET_MOUNT_INVALID")
        self.compose(
            "exec",
            "-T",
            "--user",
            "10001:10001",
            "online-worker",
            "python",
            "-c",
            WORKER_IDENTITY_PROBE + (APP_SECRET_USER_PROBE if self.mode == "app" else ""),
        )
        self.compose(
            "exec",
            "-T",
            "--user",
            "0:0",
            "online-worker",
            "python",
            "-c",
            APP_SECRET_ROOT_PROBE if self.mode == "app" else WEB_SECRET_ROOT_PROBE,
        )

    def volume_identity(self):
        result = {}
        for name in ("uploads", "postgres", "redis", "pocketbase"):
            value = json.loads(
                self.run(["docker", "volume", "inspect", self.project + "_" + name])
            )[0]
            if value["Labels"].get("com.docker.compose.project") != self.project:
                raise DeployError("FOREIGN_VOLUME")
            result[name] = value["CreatedAt"]
        return result

    def production_snapshot(self):
        """Read identity fields only, never production env/config/database/Secret."""
        result = {}
        ids = self.run(
            ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=storylens-online"]
        ).splitlines()
        for identifier in sorted(ids):
            if not re.fullmatch(r"[a-f0-9]{12,64}", identifier):
                raise DeployError("INVALID_CONTAINER_ID")
            result[identifier] = self.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.Id}} {{.Image}} {{.RestartCount}}",
                    identifier,
                ]
            )
        volumes = self.run(
            [
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                "label=com.docker.compose.project=storylens-online",
            ]
        ).splitlines()
        for name in sorted(volumes):
            if not re.fullmatch(r"storylens-online_[a-z_]+", name):
                raise DeployError("INVALID_VOLUME_NAME")
            result[name] = self.run(
                ["docker", "volume", "inspect", "--format", "{{.CreatedAt}}", name]
            )
        for name in ("current", "current-web", "current-app", "shared/lightweight-compose.json"):
            path = Path("/opt/storylens") / name
            if path.is_symlink():
                result[name] = os.readlink(path)
            elif path.exists():
                info = path.stat()
                result[name] = [info.st_ino, info.st_size, info.st_mtime_ns]
            else:
                result[name] = None
        return result

    def log_safety(self):
        """Only fixed fake value is known here; capture native output, never print it."""
        forbidden = TEST_KEY.decode()
        outputs = [self.compose("config", "--format", "json"), self.compose("logs", "--no-color")]
        for identifier in self.ids().values():
            outputs.append(self.run(["docker", "inspect", identifier]))
        for mode in ("web", "app"):
            outputs.append(
                self.run(
                    ["docker", "image", "history", "--no-trunc", f"{self.project}-{mode}:baseline"]
                )
            )
        for image in {self.inspect(identifier)["Image"] for identifier in self.ids().values()}:
            outputs.append(self.run(["docker", "image", "history", "--no-trunc", image]))
        if any(forbidden in value for value in outputs):
            raise DeployError("SECRET_SAFETY_FAILED")

    def validate(self, candidate: Path):
        paths(self.project, self.state, self.evidence, candidate)
        if (self.state / "pending.json").exists():
            raise DeployError("MANUAL_RECOVERY_REQUIRED")
        if candidate != self.root / "candidates" / self.mode:
            raise DeployError("MODE_MISMATCH")
        trusted(self.state / "session.json")
        record = json.loads((self.state / "session.json").read_text())
        spec = json.loads((self.state / "compose.json").read_text())
        if record["mode"] != self.mode or record["project"] != self.project or not record["ready"]:
            raise DeployError("ACCEPTANCE_NOT_READY")
        # Only image and health fields may differ from our generated configuration;
        # the actual allowed last state is also pinned in the root-owned record.
        if spec != record["spec"]:
            raise DeployError("ACCEPTANCE_CONFIG_DRIFT")
        expected = compose_spec(self.project, self.state, self.mode)
        for name in ("online-api", "online-worker", "schema-init"):
            expected["services"][name]["image"] = record["baseline_images"]["app"]
        expected["services"]["online-web"]["image"] = record["baseline_images"]["web"]
        for name in TARGETS[self.mode]:
            expected["services"][name]["image"] = spec["services"][name]["image"]
        if spec != expected:
            raise DeployError("ACCEPTANCE_CONFIG_DRIFT")
        old, new = tree_hashes(self.root / "baseline"), tree_hashes(candidate)
        if old != record["baseline"] or new != record["candidates"][self.mode]:
            raise DeployError("SOURCE_HASH_MISMATCH")
        require_mode([n for n in old.keys() | new.keys() if old.get(n) != new.get(n)], self.mode)
        if (self.state / "pending.json").exists():
            raise DeployError("MANUAL_RECOVERY_REQUIRED")
        return record, spec

    def update(self, candidate: Path, fault: str, dry_run: bool):
        if fault not in ("none", "health", "worker", "rollback") or (
            fault == "worker" and self.mode != "app"
        ):
            raise DeployError("INVALID_FAULT")
        record, spec = self.validate(candidate)
        self.audit_containers()
        self.before_volumes = self.volume_identity()
        self.before_production = self.production_snapshot()
        before = self.ids()
        images = {n: self.inspect(i)["Image"] for n, i in before.items()}
        db_before = self.database_fingerprint()
        self.secret_boundary(record_evidence=not dry_run)
        if dry_run:
            return "DRY_RUN_OK"
        tag = f"{self.project}-{self.mode}:candidate-{time.time_ns()}"
        image = self.build(candidate, self.mode, tag, record["candidates"][self.mode])
        old_spec = copy.deepcopy(spec)
        # Pin immutable IDs, not mutable baseline tags, for the group rollback.
        for name in TARGETS[self.mode]:
            old_spec["services"][name]["image"] = images[name]
            spec["services"][name]["image"] = image
        write_json(self.state / "pending.json", {"rollback_spec": old_spec})
        try:
            if fault in ("health", "rollback"):
                service = "online-web" if self.mode == "web" else "online-api"
                spec["services"][service]["healthcheck"] = health(["sh", "-c", "exit 1"])
            elif fault == "worker":
                spec["services"]["online-worker"]["command"] = ["sh", "-c", "exit 1"]
            write_json(self.state / "compose.json", spec)
            self.compose(
                "up", "-d", "--no-build", "--force-recreate", "--no-deps", *TARGETS[self.mode]
            )
            self.wait(TARGETS[self.mode])
            self.verify_after(before, db_before)
            if self.mode == "web":
                page = self.compose(
                    "exec", "-T", "online-web", "wget", "-qO-", "http://127.0.0.1:8080/"
                )
                if "storylens-acceptance" not in page or "candidate-v2" not in page:
                    raise DeployError("CANDIDATE_MARKER_MISSING")
        except BaseException:  # noqa: BLE001 -- rollback on interruption; no raw errors
            try:
                write_json(self.state / "compose.json", old_spec)
                if fault == "rollback":
                    raise DeployError("INJECTED_ROLLBACK_FAILURE")
                self.compose(
                    "up", "-d", "--no-build", "--force-recreate", "--no-deps", *TARGETS[self.mode]
                )
                self.wait(TARGETS[self.mode])
                self.verify_after(before, db_before)
                for name in TARGETS[self.mode]:
                    if self.inspect(self.ids()[name])["Image"] != images[name]:
                        raise DeployError("ROLLBACK_IMAGE_MISMATCH")
                record["spec"] = old_spec
                write_json(self.state / "session.json", record)
                self.record("UPDATE_FAILED_ROLLBACK_OK", before, self.ids())
                (self.state / "pending.json").unlink()
            except BaseException:  # noqa: BLE001 -- fixed error, preserve recovery marker
                raise DeployError("ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED") from None
            raise DeployError("UPDATE_FAILED_ROLLBACK_OK") from None
        record["spec"] = spec
        write_json(self.state / "session.json", record)
        self.record("UPDATE_OK", before, self.ids())
        (self.state / "pending.json").unlink()
        return "UPDATE_OK"

    def verify_after(self, before, db_before):
        self.audit_containers()
        if self.before_volumes != self.volume_identity():
            raise DeployError("VOLUME_CHANGED")
        if self.before_production != self.production_snapshot():
            raise DeployError("PRODUCTION_CHANGED")
        after = self.ids()
        if any(after[n] != before[n] for n in SERVICES if n not in TARGETS[self.mode]):
            raise DeployError("UNRELATED_CONTAINER_CHANGED")
        if db_before != self.database_fingerprint():
            raise DeployError("DATABASE_CHANGED")
        self.secret_boundary()
        self.log_safety()

    def record(self, status, before, after):
        write_json(
            self.evidence / f"{time.time_ns()}.json",
            {
                "status": status,
                "project": self.project,
                "mode": self.mode,
                "before": before,
                "after": after,
                "database_unchanged": True,
            },
        )
