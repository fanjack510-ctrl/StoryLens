"""Real probe scripts, Fake Docker orchestration and opt-in Linux kernel permissions."""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_acceptance as acceptance
import test_deploy_acceptance as acceptance_tests
from deploy_policy import DeployError


@pytest.fixture
def session(tmp_path, monkeypatch):
    return acceptance_tests.session.__wrapped__(tmp_path, monkeypatch)


def probe_for(code, runtime, original=None):
    code = code.replace("/run/storylens-online", runtime.as_posix())
    if original is not None:
        code = code.replace("/run/secrets/storylens_online_deepseek_api_key", original.as_posix())
    return code


@pytest.mark.parametrize("mode", ["web", "app"])
def test_split_users_mounts_and_success_evidence(session, mode):
    deployment, fake, _ = session(mode)
    deployment.secret_boundary()
    calls = [c for c in fake.calls if "exec" in c and "python" in c]
    assert len(calls) == 2
    assert calls[0][calls[0].index("--user") + 1] == "10001:10001"
    assert calls[1][calls[1].index("--user") + 1] == "0:0"
    if mode == "web":
        assert calls[0][-1] == acceptance.WORKER_IDENTITY_PROBE
        assert "deepseek" not in calls[0][-1]
        assert "lstat" in calls[1][-1] and "read" not in calls[1][-1]
    else:
        assert "os.open" in calls[0][-1] and "PermissionError" in calls[0][-1]
        assert "values[0] == values[1]" in calls[1][-1]
    records = list(deployment.evidence.glob("secret-boundary-*.json"))
    assert (
        len(records) == 1 and json.loads(records[0].read_text())["status"] == "SECRET_BOUNDARY_OK"
    )


@pytest.mark.parametrize("where", ["identity", "root", "tmpfs", "mount", "inspect"])
def test_every_boundary_failure_retains_fixed_evidence(session, where, capsys):
    deployment, fake, _ = session("web")
    marker = "PRIVATE_TEST_ERROR_MUST_NOT_ESCAPE"

    def run(args, timeout=120):
        if where == "inspect" and args[:2] == ["docker", "inspect"]:
            raise PermissionError(marker)
        if "--user" in args:
            user = args[args.index("--user") + 1]
            if (where == "identity" and user == "10001:10001") or (
                where == "root" and user == "0:0"
            ):
                raise PermissionError(marker)
        return fake(args, timeout)

    def tamper(name, info):
        if where == "tmpfs":
            info["HostConfig"]["Tmpfs"] = {}
        if where == "mount":
            info["Mounts"] = [{"Type": "bind", "Source": marker, "RW": False}]

    deployment.run = run
    fake.tamper = tamper
    before = (deployment.state / "session.json").read_bytes()
    with pytest.raises(DeployError, match="^SECRET_BOUNDARY_FAILED$"):
        deployment.secret_boundary()
    records = list(deployment.evidence.glob("secret-boundary-failed-*.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text()) == {
        "status": "SECRET_BOUNDARY_FAILED",
        "mode": "web",
        "project": deployment.project,
    }
    assert marker not in records[0].read_text() + str(capsys.readouterr())
    assert (deployment.state / "session.json").read_bytes() == before
    assert fake.ids == fake.original and not any("up" in c for c in fake.calls)


@pytest.mark.parametrize("mutation", ["missing", "wrong_source", "wrong_target", "writable"])
def test_app_original_mount_is_exact_readonly_test_secret(session, mutation):
    deployment, fake, _ = session("app")

    def tamper(name, info):
        if name != "online-worker":
            return
        if mutation == "missing":
            info["Mounts"] = []
        else:
            key = {"wrong_source": "Source", "wrong_target": "Destination", "writable": "RW"}[
                mutation
            ]
            info["Mounts"][0][key] = True if key == "RW" else "/unexpected"

    fake.tamper = tamper
    with pytest.raises(DeployError, match="^SECRET_BOUNDARY_FAILED$"):
        deployment.secret_boundary()


@pytest.mark.parametrize("fails", [False, True])
def test_dry_run_boundary_does_not_write_state_or_evidence(session, fails, monkeypatch):
    deployment, _, _ = session("web")
    before = {p.name: p.read_bytes() for p in deployment.state.iterdir()}
    if fails:
        monkeypatch.setattr(
            deployment, "_secret_boundary", lambda: (_ for _ in ()).throw(PermissionError())
        )
        with pytest.raises(DeployError, match="^SECRET_BOUNDARY_FAILED$"):
            deployment.secret_boundary(record_evidence=False)
    else:
        deployment.secret_boundary(record_evidence=False)
    assert not list(deployment.evidence.iterdir())
    assert before == {p.name: p.read_bytes() for p in deployment.state.iterdir()}


@pytest.mark.parametrize(
    "kind", [None, stat.S_IFREG, stat.S_IFLNK, stat.S_IFDIR, stat.S_IFIFO, stat.S_IFCHR]
)
def test_root_lstat_probe_rejects_every_present_entry_without_reading(tmp_path, monkeypatch, kind):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    original = os.lstat
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "getegid", lambda: 0, raising=False)

    def lstat(path, *args, **kwargs):
        if Path(path) == runtime:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0, st_gid=0)
        if Path(path) == runtime / "deepseek-api-key":
            if kind is None:
                raise FileNotFoundError
            return SimpleNamespace(st_mode=kind | 0o600)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)
    code = probe_for(acceptance.WEB_SECRET_ROOT_PROBE, runtime)
    if kind is None:
        exec(code, {})  # noqa: S102 -- exact checked-in probe, no user code
    else:
        with pytest.raises(AssertionError):
            exec(code, {})  # noqa: S102 -- exact checked-in probe, no user code


def test_prepare_failure_records_secret_gate_without_marking_ready(tmp_path, monkeypatch, capsys):
    import deploy_image_contract

    monkeypatch.setattr(acceptance, "ACCEPTANCE_ROOT", tmp_path / "sessions")
    monkeypatch.setattr(acceptance, "trusted", lambda _: None)
    monkeypatch.setattr(deploy_image_contract, "trusted", lambda _: None)
    source = tmp_path / "source"
    acceptance_tests.runtime_source(source)
    monkeypatch.setattr(
        acceptance, "verify_source", lambda _: {"files": acceptance.tree_hashes(source)}
    )
    root = acceptance.ACCEPTANCE_ROOT / "sl-accept-secret20260904"
    deployment = acceptance.Acceptance(
        root.name, root / "state", root / "evidence", "web", sleep=lambda _: None
    )

    class PrepareDocker(acceptance_tests.Docker):
        def __call__(self, args, timeout=120):
            if "--user" in args and "exec" in args:
                raise PermissionError("FAKE_PRIVATE_ERROR")
            if "ls" in args or (args[:2] == ["docker", "compose"] and "up" in args):
                self.calls.append(args)
                return ""
            return super().__call__(args, timeout)

    fake = PrepareDocker(deployment)
    deployment.run = fake
    with pytest.raises(DeployError, match="^SECRET_BOUNDARY_FAILED$"):
        deployment.prepare(source, None, False)
    output = capsys.readouterr().out
    assert "IMAGE_RUNTIME_CONTRACT_OK" in output
    assert "ACCEPTANCE_BASELINE_READY" not in output and "FAKE_PRIVATE_ERROR" not in output
    assert not json.loads((deployment.state / "session.json").read_text())["ready"]
    assert list(deployment.evidence.glob("secret-boundary-failed-*.json"))
    assert not any("down" in c or "storylens-online" in c for c in fake.calls)


@pytest.mark.skipif(
    sys.platform != "linux", reason="requires real Linux root/UID 10001 permissions"
)
def test_real_linux_root0700_web_absence_and_app_permissions(session):
    if os.geteuid() != 0:
        pytest.skip("must run as root in an isolated Linux acceptance environment")
    # Standalone /tmp fixture avoids pytest's own root0700 ancestors masking the cause.
    with tempfile.TemporaryDirectory(prefix="storylens-secret-probe-") as name:
        base = Path(name)
        base.chmod(0o755)
        runtime = base / "runtime"
        runtime.mkdir(mode=0o700)
        staged = runtime / "deepseek-api-key"
        original = base / "source"
        assert runtime.stat().st_uid == runtime.stat().st_gid == 0

        def child(code, uid):
            executable = Path("/usr/bin/python3")
            if not executable.is_file():
                executable = Path(sys.executable).resolve()
            return subprocess.run(
                [str(executable), "-I", "-B", "-c", code],
                user=uid,
                group=uid,
                extra_groups=[],
                capture_output=True,
                timeout=10,
                check=False,
            )

        legacy = child(f"from pathlib import Path; Path({str(staged)!r}).exists()", 10001)
        assert legacy.returncode != 0 and b"PermissionError" in legacy.stderr
        root_probe = probe_for(acceptance.WEB_SECRET_ROOT_PROBE, runtime)
        assert child(root_probe, 0).returncode == 0
        deployment, fake, _ = session("web")

        def kernel_runner(args, timeout=120):
            if "--user" in args:
                uid = int(args[args.index("--user") + 1].split(":")[0])
                code = probe_for(args[-1], runtime).replace("/proc/1/status", "/proc/self/status")
                if child(code, uid).returncode:
                    raise DeployError("COMMAND_FAILED_SAFELY")
                return ""
            return fake(args, timeout)

        deployment.run = kernel_runner
        deployment.secret_boundary()
        assert (
            json.loads(next(deployment.evidence.glob("secret-boundary-*.json")).read_text())[
                "status"
            ]
            == "SECRET_BOUNDARY_OK"
        )
        # All real filesystem entry types tested here are rejected without reading.
        for kind in ("file", "symlink", "directory", "fifo"):
            if kind == "file":
                staged.write_bytes(b"fixed-fake-test-only")
            elif kind == "symlink":
                staged.symlink_to(base / "absent-target")
            elif kind == "directory":
                staged.mkdir()
            else:
                os.mkfifo(staged, 0o600)
            assert child(root_probe, 0).returncode != 0
            staged.rmdir() if kind == "directory" else staged.unlink()
        original.write_bytes(acceptance.TEST_KEY)
        original.chmod(0o600)
        staged.write_bytes(acceptance.TEST_KEY)
        os.chown(staged, 10001, 10001)
        staged.chmod(0o400)
        os.chown(runtime, 10001, 10001)
        user_probe = probe_for(acceptance.APP_SECRET_USER_PROBE, runtime, original)
        app_root_probe = probe_for(acceptance.APP_SECRET_ROOT_PROBE, runtime, original)
        for code, uid in ((user_probe, 10001), (app_root_probe, 0)):
            result = child(code, uid)
            assert result.returncode == 0 and not result.stdout and not result.stderr
        original.write_bytes(b"different-fake-value")
        assert child(app_root_probe, 0).returncode != 0
