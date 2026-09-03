from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra/online"
sys.path.insert(0, str(INFRA))
from deploy_package import fingerprints, members, package, preflight
from deploy_policy import BUILD, MODULE, SUPPORT, DeployError, classify, scan_secret
from deploy_runtime import (
    ALL_SERVICES,
    COMMANDS,
    LIVE_TAG,
    TARGETS,
    Deployment,
    run_command,
    validate_args,
)


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["apps/online_web/src/App.tsx"], "web"),
        (["apps/online_web/src/App.test.tsx", "infra/online/README.md"], "web"),
        (["infra/online/nginx-online.conf", "infra/online/Dockerfile.web"], "web"),
        (["apps/online_api/storylens_online/worker.py"], "app"),
        (
            ["apps/online_api/requirements.txt", "apps/online_api/tests/test_queue_contract.py"],
            "app",
        ),
        (["apps/online_api/storylens_online/db/init_schema.py"], "full"),
        (["apps/online_api/storylens_online/db/models.py"], "full"),
        (["apps/online_api/tests/test_phase2b1_schema_migration.py"], "full"),
        (["infra/online/docker-compose.yml"], "full"),
        (["infra/online/Dockerfile.api"], "full"),
        (["infra/online/worker-entrypoint.sh"], "full"),
        (["infra/online/deploy-lightweight.sh"], "full"),
        (["apps/online_api/storylens_online/services/auth.py"], "full"),
        (["apps/online_api/storylens_online/services/model_cost.py"], "full"),
        (["apps/online_web/src/secret.ts"], "full"),
        (["apps/online_web/src/api.ts"], "full"),
        (["apps/online_api/storylens_online/main.py"], "full"),
        (["apps/online_api/storylens_online/services/storage.py"], "full"),
        (["apps/online_api/storylens_online/providers/deepseek.py"], "full"),
        (["apps/online_web/src/App.tsx", "apps/online_api/storylens_online/worker.py"], "full"),
        (["unrecognized.py"], "full"),
        (["apps/online_api/storylens_online/new_module.py"], "full"),
        (["infra/online/pocketbase/pb_migrations/new.js"], "full"),
        (["docs/online/01-hong-kong-beta-foundation.md"], "documentation_only"),
        (["release/changes/CHG-20260903-001.json"], "documentation_only"),
        ([], "documentation_only"),
        (["Apps/online_web/src/App.tsx"], "full"),
        (["apps/online_api/storylens_online/Worker.py"], "full"),
        (["apps\\online_web\\src\\App.tsx"], "invalid"),
        (["apps/online_web/../../secret.py"], "invalid"),
        (["/apps/online_web/src/App.tsx"], "invalid"),
        (["C:/apps/online_web/src/App.tsx"], "invalid"),
        (["apps//online_web/src/App.tsx"], "invalid"),
        (["apps/online_web/./src/App.tsx"], "invalid"),
        (["apps/online_web/src/App.tsx\n"], "invalid"),
        (["apps/online_web/.env"], "full"),
        (["apps/online_web/node_modules/test.js"], "full"),
    ],
)
def test_classifier(paths, expected):
    assert classify(paths) == expected


def archive_bytes(content, manifest=None):
    content = dict(content)
    if manifest is not None:
        content["deployment.json"] = (json.dumps(manifest).encode(), 0o644)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, (value, mode) in content.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            member.mode = mode
            archive.addfile(member, io.BytesIO(value))
    return gzip.compress(buffer.getvalue())


class FakeDocker:
    def __init__(self, mode, failure=""):
        self.mode, self.failure = mode, failure
        self.calls = []
        self.ids = {name: hashlib.sha256(name.encode()).hexdigest() for name in ALL_SERVICES}
        self.original_ids = dict(self.ids)
        self.old = "sha256:" + "1" * 64
        self.new = "sha256:" + "2" * 64
        self.images = {value: self.old for value in self.ids.values()}
        self.tags = {LIVE_TAG[mode]: self.old}
        self.ups = 0

    def __call__(self, args, timeout=120):
        self.calls.append(args)
        if args[:3] == ["docker", "volume", "inspect"]:
            if self.failure == "volume" and self.ups:
                return '"2026-09-04T00:00:00Z"'
            return '"2026-09-01T00:00:00Z"'
        if args[:2] == ["docker", "build"]:
            self.tags[args[args.index("--tag") + 1]] = self.new
            if self.failure == "build":
                raise DeployError("COMMAND_FAILED_SAFELY")
            return ""
        if args[:3] == ["docker", "image", "tag"]:
            self.tags[args[4]] = self.tags.get(args[3], args[3])
            return ""
        if args[:2] == ["docker", "compose"]:
            if "ps" in args:
                return self.ids[args[-1]]
            assert args[args.index("up") :] == [
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                *TARGETS[self.mode],
            ]
            self.ups += 1
            for name in TARGETS[self.mode]:
                identifier = hashlib.sha256(f"{name}{self.ups}".encode()).hexdigest()
                self.ids[name] = identifier
                self.images[identifier] = self.tags[LIVE_TAG[self.mode]]
            if self.failure == "unrelated" and self.ups == 1:
                self.ids["redis"] = "e" * 64
            if self.failure == "rollback" and self.ups == 2:
                raise DeployError("COMMAND_FAILED_SAFELY")
            return ""
        if args[:2] == ["docker", "inspect"]:
            field, identifier = args[3], args[4]
            if ".Image" in field:
                return json.dumps(self.images[identifier])
            if ".RestartCount" in field:
                return "1" if self.failure == "restart" and self.ups == 1 else "0"
            assert ".State" in field
            health = "healthy"
            if self.ups == 1 and self.failure in {"health", "rollback"}:
                health = "unhealthy"
            return json.dumps({"Status": "running", "Health": {"Status": health}})
        if args[0] == "curl":
            assert "--resolve" in args and "127.0.0.1" in args[args.index("--resolve") + 1]
            return "502" if self.failure == "root" and self.ups == 1 else "200"
        raise AssertionError(args)


@pytest.fixture
def server(tmp_path):
    def make(mode="web", failure=""):
        root = tmp_path / "storylens"
        shared = root / "shared"
        stable = root / "releases" / ("a" * 8)
        shared.mkdir(parents=True)
        stable.mkdir(parents=True)
        (shared / "online.env").write_text("fake-credential-must-not-be-read")
        content = {
            name: ((INFRA / Path(name).name).read_bytes(), 0o644)
            for name in SUPPORT
            if name != "VERSION"
        }
        content["infra/online/deploy-lightweight.sh"] = (
            content["infra/online/deploy-lightweight.sh"][0],
            0o755,
        )
        content["VERSION"] = (b"1.3.6\n", 0o644)
        for name in BUILD[mode]:
            content[name] = ((ROOT / name).read_bytes(), 0o644)
        changed = MODULE[mode] + ("src/App.tsx" if mode == "web" else "storylens_online/worker.py")
        content[changed] = (b"previous source\n", 0o644)
        if mode == "app":
            content[MODULE[mode] + "storylens_online/db/models.py"] = (b"unchanged schema\n", 0o644)
        for name, (data, mode_bits) in content.items():
            path = stable / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode_bits)
        (stable / "infra/online/docker-compose.yml").write_text("trusted compose")
        os.symlink(stable, root / "current", target_is_directory=True)
        baseline_files = fingerprints(content)
        content[changed] = (b"new source\n", 0o644)
        commit, baseline = "b" * 40, "a" * 40
        manifest = {
            "protocol": 1,
            "commit": commit,
            "baseline": baseline,
            "version": "1.3.6",
            "mode": mode,
            "changed": [changed],
            "baseline_files": baseline_files,
            "files": fingerprints(content),
        }
        incoming = tmp_path / "incoming"
        incoming.mkdir()
        name = "storylens-deploy-" + "c" * 32 + ".tar.gz"
        raw = archive_bytes(content, manifest)
        (incoming / name).write_bytes(raw)
        fake = FakeDocker(mode, failure)
        deployment = Deployment(root, incoming, fake, sleep=lambda _: None)
        arguments = (
            mode,
            commit,
            name,
            hashlib.sha256(raw).hexdigest(),
            baseline,
            "app.dstorylens.com",
        )
        return deployment, fake, arguments, content, manifest

    return make


@pytest.mark.parametrize("mode", ["web", "app"])
def test_success_only_target_services_no_migration_no_secret_reads(server, mode, monkeypatch):
    deployment, fake, args, _, _ = server(mode)
    original_read = Path.read_bytes

    def safe_read(path):
        assert path.name != "online.env" and "secrets" not in path.parts
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", safe_read)
    assert deployment.deploy(*args) == "DEPLOY_SUCCEEDED"
    assert deployment.current.resolve().name == "a" * 8
    assert (deployment.root / f"current-{mode}").resolve().name == args[1]
    runtime = json.loads(deployment.override.read_text())
    assert set(runtime["services"]) == set(TARGETS[mode])
    if mode == "app":
        for name in TARGETS[mode]:
            assert runtime["services"][name]["command"] == COMMANDS[name]
    for service in set(ALL_SERVICES) - set(TARGETS[mode]):
        assert fake.ids[service] == fake.original_ids[service]
    all_commands = json.dumps(fake.calls)
    assert "init_schema" not in all_commands and "down" not in all_commands
    assert all(
        call[:3] not in (["docker", "volume", "rm"], ["docker", "volume", "create"])
        for call in fake.calls
    )
    assert "fake-credential" not in all_commands
    assert fake.ups == 1
    assert not deployment.pending.exists()


@pytest.mark.parametrize("mode", ["web", "app"])
@pytest.mark.parametrize("failure", ["health", "root", "restart"])
def test_automatic_rollback(server, mode, failure):
    deployment, fake, args, _, _ = server(mode, failure)
    with pytest.raises(DeployError, match="DEPLOY_FAILED_ROLLED_BACK"):
        deployment.deploy(*args)
    assert fake.ups == 2
    assert fake.tags[LIVE_TAG[mode]] == fake.old
    assert not (deployment.root / f"current-{mode}").exists()
    assert deployment.current.resolve().name == "a" * 8
    assert not deployment.pending.exists()


def test_pointer_failure_rolls_back_and_does_not_touch_global_current(server, monkeypatch):
    deployment, fake, args, _, _ = server()

    def fail_pointer(*_):
        raise OSError("sensitive-output-must-not-escape")

    monkeypatch.setattr(deployment, "update_pointer", fail_pointer)
    with pytest.raises(DeployError, match="^DEPLOY_FAILED_ROLLED_BACK$"):
        deployment.deploy(*args)
    assert fake.ups == 2 and fake.tags[LIVE_TAG["web"]] == fake.old
    assert deployment.current.resolve().name == "a" * 8


@pytest.mark.parametrize("reason", ["sha", "existing", "baseline", "symlink", "pending", "drift"])
def test_server_preflight_refusal_before_any_docker(server, reason):
    deployment, fake, arguments, _, _ = server()
    args = list(arguments)
    if reason == "sha":
        args[3] = "0" * 64
    if reason == "existing":
        (deployment.root / "releases" / args[1]).mkdir()
    if reason == "baseline":
        args[4] = "d" * 40
    if reason == "symlink":
        path = deployment.incoming / args[2]
        path.rename(path.with_suffix(".backup"))
        path.symlink_to(path.with_suffix(".backup"))
    if reason == "pending":
        deployment.pending.write_text("pending")
    if reason == "drift":
        (deployment.current.resolve() / "apps/online_web/src/App.tsx").write_text("drift")
    with pytest.raises((DeployError, OSError)):
        deployment.deploy(*args)
    assert not fake.calls


def test_rollback_failure_leaves_recovery_marker(server):
    deployment, _fake, args, _, _ = server("app", "rollback")
    with pytest.raises(DeployError, match="ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED"):
        deployment.deploy(*args)
    assert deployment.pending.exists()
    with pytest.raises(DeployError, match="MANUAL_RECOVERY_REQUIRED"):
        deployment.deploy(*args)


def test_unrelated_container_change_is_not_silently_accepted(server):
    deployment, fake, args, _, _ = server("web", "unrelated")
    with pytest.raises(DeployError, match="ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED"):
        deployment.deploy(*args)
    assert fake.tags[LIVE_TAG["web"]] == fake.old
    assert not (deployment.root / "current-web").exists()


@pytest.mark.parametrize(
    "name",
    ["../escape", "/escape", "a\\b", "apps/online_web/.env", "infra/online/docker-compose.yml"],
)
def test_archive_rejects_unknown_secret_paths_and_traversal(name):
    with pytest.raises(DeployError):
        members(archive_bytes({name: (b"x", 0o644)}), "web")


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_archive_rejects_symlinks_hardlinks_and_special_files(kind):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        item = tarfile.TarInfo("apps/online_web/src/App.tsx")
        item.type, item.linkname = kind, "/etc/passwd"
        archive.addfile(item)
    with pytest.raises(DeployError, match="INVALID_ARCHIVE"):
        members(buffer.getvalue(), "web")


def test_redacted_native_failures_and_literal_secret_scanner():
    fake_secret = "sk-" + "aB1c" * 12
    with pytest.raises(DeployError, match="^SECRET_PATTERN_REJECTED$"):
        scan_secret(fake_secret.encode())
    with pytest.raises(DeployError, match="^COMMAND_FAILED_SAFELY$"):
        run_command([sys.executable, "-c", f"import sys; print({fake_secret!r}); sys.exit(1)"])


@pytest.mark.parametrize(
    "field,value", [(0, "full"), (1, "../commit"), (2, "../x.tar.gz"), (3, "bad"), (5, "x.com';id")]
)
def test_strict_remote_arguments(field, value):
    args = [
        "web",
        "a" * 40,
        "storylens-deploy-" + "d" * 32 + ".tar.gz",
        "e" * 64,
        "b" * 40,
        "app.dstorylens.com",
    ]
    args[field] = value
    with pytest.raises(DeployError, match="INVALID_ARGUMENTS"):
        validate_args(*args)


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return result.stdout.decode().strip()


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "offline@example.invalid")
    git(repo, "config", "user.name", "Offline Test")
    git(repo, "config", "core.autocrlf", "false")
    for name in (*SUPPORT, *BUILD["web"], *BUILD["app"], "scripts/deploy_online.ps1"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    (repo / "apps/online_web/src").mkdir(parents=True)
    (repo / "apps/online_web/src/App.tsx").write_text("before")
    (repo / "apps/online_api/storylens_online").mkdir(parents=True)
    (repo / "apps/online_api/storylens_online/worker.py").write_text("before")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "baseline")
    baseline = git(repo, "rev-parse", "HEAD")
    (repo / "apps/online_web/src/App.tsx").write_text("after")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "web update")
    return repo, baseline


def test_local_archive_is_head_only_and_minimal(repository, tmp_path):
    repo, baseline = repository
    commit = preflight(repo, "web", baseline)["commit"]
    output = tmp_path / "package.tar.gz"
    result = package(repo, "web", baseline, output, commit)
    contents = members(output.read_bytes(), "web")
    assert contents["apps/online_web/src/App.tsx"][0] == b"after"
    assert not any(name.startswith("apps/online_api") for name in contents)
    assert "infra/online/docker-compose.yml" not in contents
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert json.loads(contents["deployment.json"][0])["baseline"] == baseline


def test_dirty_mode_docs_and_head_change_refused(repository, tmp_path):
    repo, baseline = repository
    with pytest.raises(DeployError, match="MODE_MISMATCH"):
        preflight(repo, "app", baseline)
    with pytest.raises(DeployError, match="HEAD_CHANGED"):
        package(repo, "web", baseline, tmp_path / "bad.tar.gz", "0" * 40)
    (repo / "untracked.txt").write_text("not in git")
    with pytest.raises(DeployError, match="WORKTREE_NOT_CLEAN"):
        preflight(repo, "web", baseline)


def test_shell_syntax_and_trusted_entrypoint():
    shell = (
        Path(r"C:\Program Files\Git\bin\sh.exe") if os.name == "nt" else Path(shutil.which("sh"))
    )
    result = subprocess.run(
        [str(shell), "-n", str(INFRA / "deploy-lightweight.sh")], capture_output=True, check=False
    )
    assert result.returncode == 0
    source = (INFRA / "deploy-lightweight.sh").read_bytes()
    assert b"\r" not in source and b"set -eu" in source
    assert b"python3 -I" in source and b"exec " in source


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell entrypoint")
@pytest.mark.parametrize(
    "case,expected",
    [
        ("dirty", "WORKTREE_NOT_CLEAN"),
        ("mode", "MODE_MISMATCH"),
        ("dry", "DRY_RUN_OK"),
        ("full", "FULL_DEPLOYMENT_REQUIRED"),
        ("docs", "DOCUMENTATION_ONLY"),
    ],
)
def test_powershell_offline_preflight(repository, case, expected):
    repo, baseline = repository
    if case == "docs":
        baseline = git(repo, "rev-parse", "HEAD")
        (repo / "infra/online/README.md").write_text("documentation only")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "docs")
    if case == "dirty":
        (repo / "dirty.txt").write_text("x")
    if case == "full":
        (repo / "infra/online/docker-compose.yml").write_text("high risk")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "full")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo / "scripts/deploy_online.ps1"),
        "-Mode",
        "app" if case == "mode" else "web",
        "-Server",
        "ubuntu@offline.invalid",
        "-IdentityFile",
        str(repo / "key never read"),
        "-BaselineCommit",
        baseline,
        "-DryRun",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    assert expected in result.stdout, (result.stdout, result.stderr)
    assert result.returncode == (0 if case == "dry" else 1)
    assert not result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell native transport")
@pytest.mark.parametrize("failure", ["", "scp", "ssh", "secret"])
def test_powershell_fake_scp_ssh_end_to_end(repository, tmp_path, failure):
    repo, baseline = repository
    fake_bin = tmp_path / "fake tools"
    fake_bin.mkdir()
    identity = tmp_path / "not a real key's file"
    identity.write_text("not a credential")
    helper = fake_bin / "fake_native.py"
    log = tmp_path / "transport.jsonl"
    remote = tmp_path / "remote-package.tar.gz"
    helper.write_text(
        """import hashlib, json, os, pathlib, shlex, shutil, sys
kind, *args = sys.argv[1:]
with open(os.environ['TEST_TRANSPORT_LOG'], 'a') as log:
    log.write(json.dumps([kind, *args]) + '\\n')
failure = os.environ['TEST_TRANSPORT_FAILURE']
if kind == 'scp':
    if failure == 'scp':
        print('transport error must not escape'); sys.exit(1)
    shutil.copyfile(args[-2], os.environ['TEST_REMOTE_ARCHIVE'])
else:
    tokens = shlex.split(args[-1])
    assert tokens[:3] == ['sudo', '-n', '/opt/storylens/current/infra/online/deploy-lightweight.sh']
    mode, commit, filename, digest, baseline, domain = tokens[3:]
    assert mode == 'web' and len(commit) == 40 and len(baseline) == 40
    assert hashlib.sha256(pathlib.Path(os.environ['TEST_REMOTE_ARCHIVE']).read_bytes()).hexdigest() == digest
    assert domain == 'app.dstorylens.com'
    if failure == 'ssh':
        print('DEPLOY_FAILED_ROLLED_BACK'); sys.exit(1)
    if failure == 'secret':
        print('sk-' + 'z9' * 24); sys.exit(1)
    print('DEPLOY_SUCCEEDED')
""",
        encoding="utf-8",
    )
    for name in ("ssh", "scp"):
        (fake_bin / f"{name}.cmd").write_text(
            f'@"{sys.executable}" "{helper}" {name} %*\n',
            encoding="utf-8",
        )
    env = {
        **os.environ,
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
        "TEST_TRANSPORT_LOG": str(log),
        "TEST_REMOTE_ARCHIVE": str(remote),
        "TEST_TRANSPORT_FAILURE": failure,
    }
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo / "scripts/deploy_online.ps1"),
        "-Mode",
        "web",
        "-Server",
        "ubuntu@offline.invalid",
        "-IdentityFile",
        str(identity),
        "-BaselineCommit",
        baseline,
        "-SkipTests",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=90, env=env, check=False
    )
    assert result.returncode == (1 if failure else 0), (result.stdout, result.stderr)
    assert "SKIP_TESTS_EXPLICIT" in result.stdout
    assert "sk-" + "z9" * 24 not in result.stdout + result.stderr
    assert "transport error" not in result.stdout + result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [call[0] for call in calls] == (["scp"] if failure == "scp" else ["scp", "ssh"])
    assert "StrictHostKeyChecking=yes" in calls[0]
    assert str(identity) in calls[0]  # path with spaces/apostrophe survived native quoting
    assert "not a credential" not in json.dumps(calls)
    assert not Path(calls[0][-2]).exists()  # only the task-created local package was removed
    if not failure:
        assert "DEPLOY_SUCCEEDED mode=web" in result.stdout
        assert members(remote.read_bytes(), "web")["apps/online_web/src/App.tsx"][0] == b"after"


def test_server_rejects_forged_manifest_hiding_schema_change(server):
    deployment, fake, args, content, manifest = server("app")
    content["apps/online_api/storylens_online/db/models.py"] = (b"forbidden change", 0o644)
    manifest["files"] = fingerprints(content)
    raw = archive_bytes(content, manifest)
    (deployment.incoming / args[2]).write_bytes(raw)
    args = (*args[:3], hashlib.sha256(raw).hexdigest(), *args[4:])
    with pytest.raises(DeployError, match="FULL_DEPLOYMENT_REQUIRED"):
        deployment.deploy(*args)
    assert not fake.calls


def test_failed_build_does_not_change_containers_or_pointers(server):
    deployment, fake, args, _, _ = server("web", "build")
    with pytest.raises(DeployError, match="COMMAND_FAILED_SAFELY"):
        deployment.deploy(*args)
    assert fake.ups == 0
    assert fake.ids == fake.original_ids
    assert not deployment.override.exists()


def test_preserves_other_component_override(server):
    deployment, fake, args, _, _ = server("web")
    runtime = {
        "services": {
            name: {"image": LIVE_TAG["app"], "command": COMMANDS[name]} for name in TARGETS["app"]
        }
    }
    deployment.override.write_text(json.dumps(runtime))
    deployment.deploy(*args)
    updated = json.loads(deployment.override.read_text())
    for name in TARGETS["app"]:
        assert updated["services"][name] == runtime["services"][name]
        assert fake.ids[name] == fake.original_ids[name]


def test_source_equivalent_baseline_allows_alternating_component_history(server):
    deployment, fake, args, content, manifest = server("web")
    manifest["baseline"] = "d" * 40
    raw = archive_bytes(content, manifest)
    (deployment.incoming / args[2]).write_bytes(raw)
    args = (*args[:3], hashlib.sha256(raw).hexdigest(), "d" * 40, args[5])
    assert deployment.deploy(*args) == "DEPLOY_SUCCEEDED"
    assert fake.ups == 1


def test_changed_volume_blocks_success_and_requires_manual_recovery(server):
    deployment, fake, args, _, _ = server("app", "volume")
    with pytest.raises(DeployError, match="ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED"):
        deployment.deploy(*args)
    assert fake.tags[LIVE_TAG["app"]] == fake.old
    assert deployment.pending.exists()


def test_rollback_after_pointer_replacement_restores_previous_pointer(server, monkeypatch):
    deployment, fake, args, _, _ = server("web")
    switch = deployment.update_pointer

    def fail_after_switch(*args):
        switch(*args)
        raise OSError("safe failure")

    monkeypatch.setattr(deployment, "update_pointer", fail_after_switch)
    with pytest.raises(DeployError, match="DEPLOY_FAILED_ROLLED_BACK"):
        deployment.deploy(*args)
    assert not (deployment.root / "current-web").exists()
    assert fake.tags[LIVE_TAG["web"]] == fake.old


@pytest.mark.parametrize("mode", ["web", "app"])
def test_real_compose_render_merges_only_target_override_without_engine(tmp_path, mode):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose CLI unavailable; no runtime required")
    override = tmp_path / "override.json"
    services = {}
    for name in TARGETS[mode]:
        services[name] = {"image": LIVE_TAG[mode]}
        if name in COMMANDS:
            services[name]["command"] = COMMANDS[name]
    override.write_text(json.dumps({"services": services}))
    base = [
        docker,
        "compose",
        "--project-name",
        "storylens-online",
        "--project-directory",
        str(INFRA),
        "--env-file",
        str(INFRA / ".env.example"),
        "-f",
        str(INFRA / "docker-compose.yml"),
    ]

    def render(extra):
        result = subprocess.run(
            [*base, *extra, "config", "--format", "json"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0  # do not print rendered environment
        return json.loads(result.stdout)

    original = render([])
    merged = render(["-f", str(override)])
    for name in ALL_SERVICES:
        if name not in TARGETS[mode]:
            assert original["services"][name] == merged["services"][name]
        else:
            expected = {**original["services"][name], **services[name]}
            assert expected == merged["services"][name]
    assert original["volumes"] == merged["volumes"]
    assert original["networks"] == merged["networks"]
    assert original["secrets"] == merged["secrets"]
