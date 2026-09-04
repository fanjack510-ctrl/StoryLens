import hashlib
import json
import sys
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
import deploy_acceptance as acceptance
import deploy_install as installer
from deploy_acceptance import SERVICES, Acceptance, compose_spec, paths, project_name, tree_hashes
from deploy_cli import parse
from deploy_policy import DeployError
from deploy_protocol import PROTOCOL, TOOL_FILES, check_protocol, tool_version
from deploy_runtime import COMMANDS, TARGETS


class Docker:
    """Execute the update orchestration, fake only Docker's OS boundary."""

    def __init__(self, session):
        self.session, self.calls, self.ups = session, [], 0
        self.ids = {n: hashlib.sha256(n.encode()).hexdigest() for n in SERVICES}
        self.original = dict(self.ids)
        self.old = "sha256:" + "1" * 64
        self.new = "sha256:" + "2" * 64
        self.images = {n: self.old for n in SERVICES}
        self.health_failed = set()
        self.exit_failed = set()
        self.tamper = None

    def __call__(self, args, timeout=120):
        self.calls.append(args)
        project = self.session.project
        if args[:3] == ["docker", "ps", "-aq"] or args[:4] == ["docker", "volume", "ls", "-q"]:
            return ""
        if args[:3] == ["docker", "image", "history"]:
            return "safe history"
        if args[:2] == ["docker", "build"]:
            assert str(self.session.root) in args[-1]
            return ""
        if args[:3] == ["docker", "network", "inspect"]:
            return json.dumps(
                [{"Internal": True, "Labels": {"com.docker.compose.project": project}}]
            )
        if args[:3] == ["docker", "volume", "inspect"]:
            return json.dumps(
                [{"CreatedAt": "original", "Labels": {"com.docker.compose.project": project}}]
            )
        if args[:2] == ["docker", "inspect"]:
            name = next(n for n, v in self.ids.items() if v == args[2])
            labels = {"com.docker.compose.project": project}
            mounts = []
            if name == "online-worker" and self.session.mode == "app":
                mounts.append(
                    {
                        "Type": "bind",
                        "Source": str(self.session.state / "test_provider"),
                        "RW": False,
                    }
                )
            value = {
                "Image": self.images[name],
                "Config": {"Labels": labels},
                "HostConfig": {
                    "Tmpfs": {"/run/storylens-online": "rw,noexec,nosuid,nodev,size=64k,mode=0700"}
                },
                "NetworkSettings": {"Networks": {project + "_isolated": {}}},
                "Mounts": mounts,
                "State": {
                    "Status": "exited" if name in self.exit_failed else "running",
                    "Health": {"Status": "unhealthy" if name in self.health_failed else "healthy"},
                },
                "RestartCount": 0,
            }
            if self.tamper:
                self.tamper(name, value)
            return json.dumps([value])
        assert args[:2] == ["docker", "compose"]
        assert args[args.index("--project-name") + 1] == project
        if "ps" in args:
            return self.ids[args[-1]]
        if "config" in args:
            return (self.session.state / "compose.json").read_text()
        if "logs" in args:
            return "safe logs"
        if "up" in args:
            self.ups += 1
            spec = json.loads((self.session.state / "compose.json").read_text())
            targets = args[args.index("--no-deps") + 1 :]
            assert tuple(targets) == TARGETS[self.session.mode]
            self.health_failed.clear()
            self.exit_failed.clear()
            for name in targets:
                service = spec["services"][name]
                self.ids[name] = hashlib.sha256((name + str(self.ups)).encode()).hexdigest()
                self.images[name] = self.old if service["image"] == self.old else self.new
                if "exit 1" in service.get("healthcheck", {}).get("test", []):
                    self.health_failed.add(name)
                if "exit 1" in service.get("command", []):
                    self.exit_failed.add(name)
            return ""
        if "pg_dump" in args:
            return "schema original"
        if "psql" in args:
            return "0|0|0"
        if "wget" in args:
            return '<meta name="storylens-acceptance" content="candidate-v2">'
        assert "exec" in args and "python" in args  # Worker UID/tmpfs assertion command
        return ""


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance, "ACCEPTANCE_ROOT", tmp_path)
    # Filesystem ownership is separately covered; temporary Linux pytest parents
    # are intentionally not a privileged deployment installation.
    monkeypatch.setattr(acceptance, "trusted", lambda p: None)

    def make(mode):
        root = tmp_path / ("sl-accept-" + mode + "12345678")
        state, evidence = root / "state", root / "evidence"
        state.mkdir(parents=True)
        evidence.mkdir()
        baseline, candidate = root / "baseline", root / "candidates" / mode
        name = (
            "apps/online_web/index.html"
            if mode == "web"
            else "apps/online_api/storylens_online/errors.py"
        )
        for directory, value in ((baseline, "before"), (candidate, "after")):
            (directory / name).parent.mkdir(parents=True)
            (directory / name).write_text(value)
        spec = compose_spec(root.name, state, mode)
        record = {
            "mode": mode,
            "project": root.name,
            "ready": True,
            "spec": spec,
            "baseline": tree_hashes(baseline),
            "candidates": {mode: tree_hashes(candidate)},
        }
        (state / "session.json").write_text(json.dumps(record))
        (state / "compose.json").write_text(json.dumps(spec))
        result = Acceptance(root.name, state, evidence, mode, sleep=lambda _: None)
        fake = Docker(result)
        result.run = fake
        return result, fake, candidate

    return make


@pytest.mark.parametrize("mode", ["web", "app"])
@pytest.mark.parametrize("fault", ["none", "health", "rollback"])
def test_real_orchestration_success_rollback_stop(session, mode, fault):
    deployment, fake, candidate = session(mode)
    if fault == "none":
        assert deployment.update(candidate, fault, False) == "UPDATE_OK"
    else:
        code = (
            "UPDATE_FAILED_ROLLBACK_OK"
            if fault == "health"
            else "ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED"
        )
        with pytest.raises(DeployError, match=code):
            deployment.update(candidate, fault, False)
    assert (deployment.state / "pending.json").exists() == (fault == "rollback")
    for name in SERVICES:
        if name not in TARGETS[mode]:
            assert fake.ids[name] == fake.original[name]
    assert all("storylens-online" != arg for cmd in fake.calls for arg in cmd)
    updates = [c for c in fake.calls if "up" in c]
    assert updates and all("schema-init" not in c and "init_schema" not in str(c) for c in updates)
    if fault == "health":
        assert fake.ups == 2 and all(fake.images[n] == fake.old for n in TARGETS[mode])
    if fault == "rollback":
        count = len(fake.calls)
        with pytest.raises(DeployError, match="MANUAL_RECOVERY_REQUIRED"):
            deployment.update(candidate, "none", False)
        assert len(fake.calls) == count


def test_worker_fault_rolls_back_group(session):
    deployment, fake, candidate = session("app")
    with pytest.raises(DeployError, match="UPDATE_FAILED_ROLLBACK_OK"):
        deployment.update(candidate, "worker", False)
    assert fake.ups == 2
    assert fake.images["online-api"] == fake.old == fake.images["online-worker"]


@pytest.mark.parametrize("mode", ["web", "app"])
def test_dry_run_does_not_write_or_update(session, mode):
    deployment, fake, candidate = session(mode)
    before = tree_hashes(deployment.root)
    assert deployment.update(candidate, "none", True) == "DRY_RUN_OK"
    assert tree_hashes(deployment.root) == before
    assert not any("up" in c or "build" in c for c in fake.calls)


@pytest.mark.parametrize("mutation", ["port", "network", "volume", "bind", "label", "privileged"])
def test_cannot_prove_isolation_refuses_before_build(session, mutation):
    deployment, fake, candidate = session("web")

    def tamper(name, value):
        if mutation == "port":
            value["HostConfig"]["PortBindings"] = {"80/tcp": [{}]}
        if mutation == "network":
            value["NetworkSettings"]["Networks"] = {"storylens-online_private": {}}
        if mutation == "volume":
            value["Mounts"] = [{"Type": "volume", "Name": "storylens-online_postgres_data"}]
        if mutation == "bind":
            value["Mounts"] = [
                {"Type": "bind", "Source": "/opt/storylens/shared/secrets/key", "RW": False}
            ]
        if mutation == "label":
            value["Config"]["Labels"]["com.docker.compose.project"] = "storylens-online"
        if mutation == "privileged":
            value["HostConfig"]["Privileged"] = True

    fake.tamper = tamper
    with pytest.raises(DeployError):
        deployment.update(candidate, "none", False)
    assert not any("build" in c or "up" in c for c in fake.calls)


@pytest.mark.parametrize(
    "project",
    [
        "storylens-online",
        "sl-accept-../foo",
        "sl-accept-a;id",
        "sl-accept-ABC123456",
        "sl-accept-short",
        "sl-accept-12345678\n",
    ],
)
def test_bad_project(project):
    with pytest.raises(DeployError):
        project_name(project)


@pytest.mark.parametrize("field", ["state", "evidence", "candidate"])
def test_bad_paths(field):
    args = [
        "sl-accept-12345678",
        Path("/opt/storylens/acceptance/sl-accept-12345678/state"),
        Path("/opt/storylens/acceptance/sl-accept-12345678/evidence"),
        Path("/opt/storylens/acceptance/sl-accept-12345678/candidates/web"),
    ]
    args[{"state": 1, "evidence": 2, "candidate": 3}[field]] = Path("/opt/storylens/shared")
    with pytest.raises(DeployError):
        paths(*args)


def test_production_fault_argument_rejected():
    with pytest.raises(DeployError):
        parse(
            [
                "production",
                "--fault",
                "health",
                "web",
                "a" * 40,
                "storylens-deploy-" + "d" * 32 + ".tar.gz",
                "e" * 64,
                "b" * 40,
                "app.dstorylens.com",
            ]
        )


def test_protocol_mismatch():
    version = tool_version(INFRA)
    check_protocol(PROTOCOL, version, INFRA)
    for protocol, expected in ((1, version), (2, "0" * 64)):
        with pytest.raises(DeployError, match="PROTOCOL_MISMATCH"):
            check_protocol(protocol, expected, INFRA)


@pytest.mark.parametrize("mode", ["web", "app"])
def test_closed_compose_contract(mode):
    spec = compose_spec("sl-accept-12345678", Path("/isolated/state"), mode)
    assert spec["networks"] == {"isolated": {"internal": True}}
    for name, service in spec["services"].items():
        assert not any(
            k in service
            for k in (
                "ports",
                "env_file",
                "build",
                "container_name",
                "privileged",
                "extends",
                "network_mode",
            )
        )
        assert service["networks"] == ["isolated"]
        assert all(not str(v).startswith("/") for v in service.get("volumes", []))
        if name in COMMANDS:
            assert service["command"] == COMMANDS[name]
        provider = [s for s in service.get("secrets", []) if isinstance(s, dict)]
        assert bool(provider) == (mode == "app" and name == "online-worker")
    assert ("test_provider" in spec["secrets"]) == (mode == "app")


def test_installer_roundtrip_and_unknown_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "trusted", lambda p: None)
    source = tmp_path / "source"
    tools = source / "infra/online"
    tools.mkdir(parents=True)
    files = {}
    for name in TOOL_FILES:
        value = (INFRA / name).read_bytes()
        (tools / name).write_bytes(value)
        files["infra/online/" + name] = hashlib.sha256(value).hexdigest()
    meta = {
        "commit": "a" * 40,
        "protocol": PROTOCOL,
        "tool_version": tool_version(tools),
        "files": files,
    }
    (source / "bootstrap.json").write_text(json.dumps(meta))
    lib, entry = tmp_path / "lib", tmp_path / "bin/entry"
    assert installer.install(source, lib, entry)["tool_version"] == meta["tool_version"]
    assert entry.resolve() == lib / ("a" * 40) / "deploy-lightweight.sh"
    assert installer.install(source, lib, entry)["commit"] == "a" * 40
    assert list(entry.parent.glob("previous-tool-*.json"))
    # Same named version with unknown bytes is not repaired/overwritten silently.
    target = lib / ("a" * 40) / "deploy_runtime.py"
    target.chmod(0o644)
    target.write_text("unknown")
    with pytest.raises(DeployError):
        installer.install(source, lib, entry)
    assert target.read_text() == "unknown"


def test_no_current_tool_dependency():
    source = (INFRA.parent.parent / "scripts/deploy_online.ps1").read_text()
    assert "/opt/storylens/bin/storylens-online-deploy-lightweight" in source
    assert "/opt/storylens/current/infra/online" not in source
    assert "--protocol 2" in source
    from deploy_policy import SUPPORT

    assert SUPPORT == ("VERSION",)


@pytest.mark.parametrize(
    "uid,gid,mode,link",
    [
        (1000, 0, 0o755, False),
        (0, 1000, 0o755, False),
        (0, 0, 0o775, False),
        (0, 0, 0o757, False),
        (0, 0, 0o755, True),
    ],
)
def test_privileged_path_rejects_unsafe_ownership(uid, gid, mode, link, monkeypatch):
    from types import SimpleNamespace

    import deploy_protocol

    class FakePath:
        parents = ()

        def lstat(self):
            return SimpleNamespace(st_uid=uid, st_gid=gid, st_mode=mode)

        def is_symlink(self):
            return link

    # Limit the platform override to the module's view (not global os.name).
    monkeypatch.setattr(deploy_protocol, "os", SimpleNamespace(name="posix"))
    with pytest.raises(ValueError, match="UNTRUSTED_PATH"):
        deploy_protocol.trusted(FakePath())


def test_prepare_dry_run_and_first_bootstrap_only_migrates_isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance, "ACCEPTANCE_ROOT", tmp_path / "sessions")
    monkeypatch.setattr(acceptance, "trusted", lambda p: None)
    source = tmp_path / "source"
    names = ["apps/online_web/index.html", "apps/online_api/storylens_online/errors.py"]
    for name in names:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<head></head>" if name.endswith(".html") else "# baseline\n")
    monkeypatch.setattr(acceptance, "verify_source", lambda p: {"files": names})
    project = "sl-accept-prepare1234"
    root = acceptance.ACCEPTANCE_ROOT / project
    deployment = Acceptance(project, root / "state", root / "evidence", "web", sleep=lambda _: None)

    class PrepareDocker(Docker):
        def __call__(self, args, timeout=120):
            if "ls" in args or (args[:2] == ["docker", "compose"] and "up" in args):
                self.calls.append(args)
                return ""
            return super().__call__(args, timeout)

    fake = PrepareDocker(deployment)
    deployment.run = fake
    assert deployment.prepare(source, None, True) == "DRY_RUN_OK"
    assert not root.exists()
    assert deployment.prepare(source, None, False) == "ACCEPTANCE_BASELINE_READY"
    assert not (root / "state/test_provider").exists()
    schema_calls = [c for c in fake.calls if "up" in c and "schema-init" in c]
    assert len(schema_calls) == 1 and project in schema_calls[0]
    assert json.loads((root / "state/session.json").read_text())["ready"]
    with pytest.raises(DeployError, match="ACCEPTANCE_ALREADY_EXISTS"):
        deployment.prepare(source, None, False)


@pytest.mark.parametrize("mode", ["web", "app"])
def test_real_compose_cli_accepts_closed_spec(tmp_path, mode):
    import shutil
    import subprocess

    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Compose CLI unavailable")
    path = tmp_path / "compose.json"
    path.write_text(json.dumps(compose_spec("sl-accept-render1234", tmp_path, mode)))
    result = subprocess.run(
        [docker, "compose", "-f", str(path), "config", "--format", "json"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0  # raw rendering is intentionally not emitted
    config = json.loads(result.stdout)
    assert config["networks"]["isolated"]["internal"]
    assert all(not value.get("ports") for value in config["services"].values())


def test_protocol_rejection_precedes_docker_or_state(monkeypatch):
    import deploy_cli

    monkeypatch.setattr(deploy_cli, "installed", lambda p: {})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_cli",
            "production",
            "--protocol",
            "999",
            "--tool-version",
            "0" * 64,
            "web",
            "a" * 40,
            "storylens-deploy-" + "b" * 32 + ".tar.gz",
            "c" * 64,
            "d" * 40,
            "app.dstorylens.com",
        ],
    )
    monkeypatch.setattr(
        deploy_cli, "Deployment", lambda: pytest.fail("must not access deployment state")
    )
    assert deploy_cli.main() == 1
