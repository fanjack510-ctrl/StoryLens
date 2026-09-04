import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_acceptance as acceptance
import deploy_image_contract as contract
import deploy_image_probe as probe
from deploy_acceptance import Acceptance, tree_hashes
from deploy_policy import DeployError
from test_deploy_acceptance import Docker, runtime_source, session  # noqa: F401 -- shared fixture


@pytest.fixture(autouse=True)
def private_test_paths(monkeypatch):
    monkeypatch.setattr(contract, "trusted", lambda p: None)
    monkeypatch.setattr(acceptance, "trusted", lambda p: None)


def test_manifest_copy_complete_and_chmod_all_nested_dirs_under_umask077(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "baseline"
    runtime_source(source)
    manifest = tree_hashes(source)
    chmods = {}
    original = Path.chmod

    def track(path, mode, **kwargs):
        chmods[path] = mode
        return original(path, mode, **kwargs)

    monkeypatch.setattr(Path, "chmod", track)
    old = os.umask(0o077)
    try:
        contract.copy_context(source, target, manifest)
    finally:
        os.umask(old)
    assert tree_hashes(target) == manifest
    assert all(chmods[p] == 0o755 for p in [target, *(p for p in target.rglob("*") if p.is_dir())])
    for name in ("db/__init__.py", "db/init_schema.py", "db/models.py", "db/phase2b1_migration.py"):
        assert (target / contract.PACKAGE / name).read_bytes() == (
            source / contract.PACKAGE / name
        ).read_bytes()
    assert tmp_path not in chmods  # never relax state/Secret ancestors


@pytest.mark.parametrize(
    "defect", ["missing", "empty_dir", "namespace", "ignore", "specific_ignore", "hash"]
)
def test_context_defects_fail_closed(tmp_path, defect):
    runtime_source(tmp_path)
    manifest = tree_hashes(tmp_path)
    if defect == "missing":
        (tmp_path / contract.PACKAGE / "db/models.py").unlink()
    elif defect == "namespace":
        (tmp_path / contract.PACKAGE / "db/__init__.py").unlink()
        manifest = tree_hashes(tmp_path)  # even a manifest missing the initializer is invalid
    elif defect == "empty_dir":
        (tmp_path / contract.PACKAGE / "empty").mkdir()
    elif defect in ("ignore", "specific_ignore"):
        path = tmp_path / (
            ".dockerignore" if defect == "ignore" else "infra/online/Dockerfile.api.dockerignore"
        )
        path.write_text("**/db/**\n")
        manifest = tree_hashes(tmp_path)
    else:
        (tmp_path / contract.PACKAGE / "db/models.py").write_text("# unexpected\n")
    with pytest.raises(DeployError, match="^BUILD_CONTEXT_CONTRACT_FAILED$"):
        contract.context_contract(tmp_path, manifest)


@pytest.mark.parametrize("defect", ["none", "missing", "namespace", "empty", "wrong_entrypoint"])
def test_real_python_probe_imports_and_nested_package_not_namespace(tmp_path, defect):
    runtime_source(tmp_path)
    package = tmp_path / contract.PACKAGE
    entrypoint = tmp_path / contract.ENTRYPOINT
    if defect == "missing":
        (package / "db/models.py").unlink()
    if defect == "namespace":
        (package / "db/__init__.py").unlink()
    if defect == "empty":
        (package / "extra").mkdir()
    if defect == "wrong_entrypoint":
        entrypoint = tmp_path / "absent"
    code = (
        "import sys; from pathlib import Path; "
        f"sys.path.insert(0,{str(Path(probe.__file__).parent)!r}); "
        f"sys.path.insert(0,{str(package.parent)!r}); "
        "from deploy_image_probe import inspect_runtime; "
        f"inspect_runtime(Path({str(package)!r}),Path({str(entrypoint)!r}))"
    )
    result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, check=False)
    assert (result.returncode == 0) == (defect == "none")


@pytest.mark.parametrize("defect", ["missing", "hash", "error", "namespace"])
def test_source_present_image_contract_failure_is_safe(tmp_path, defect):
    runtime_source(tmp_path)
    expected = contract.context_contract(tmp_path, tree_hashes(tmp_path))
    result = {"status": "IMAGE_RUNTIME_CONTRACT_OK", **expected, "modules": list(probe.MODULES)}
    # round-trip prevents mutating expected through shared dictionaries
    result = json.loads(json.dumps(result))
    if defect == "missing":
        result["files"].pop("db/models.py")
    if defect == "hash":
        result["files"]["db/models.py"] = "f" * 64
    if defect == "namespace":
        result["modules"] = []
    calls = []

    def runner(args, timeout):
        calls.append(args)
        if defect == "error":
            raise RuntimeError("FAKE_PRIVATE_TEXT_ENV_KEY")
        return json.dumps(result)

    with pytest.raises(DeployError, match="^IMAGE_RUNTIME_CONTRACT_FAILED$"):
        contract.verify_image(runner, "sha256:" + "a" * 64, expected)
    cmd = calls[0]
    assert cmd[cmd.index("--user") + 1] == "10001:10001"
    assert cmd[cmd.index("--network") + 1] == "none"
    assert not any(c in cmd for c in ("--mount", "--volume", "-v", "--env-file"))
    assert "--read-only" in cmd and "--rm" in cmd
    assert "FAKE_PRIVATE_TEXT_ENV_KEY" not in str(cmd)


def test_probe_redacts_import_output_and_exception(monkeypatch, capsys):
    monkeypatch.setattr(probe.os, "getuid", lambda: 10001, raising=False)
    monkeypatch.setattr(probe.os, "getgid", lambda: 10001, raising=False)

    def fail(*_):
        print("FAKE_PRIVATE_TEXT_ENV_KEY")
        raise RuntimeError("FAKE_PRIVATE_TEXT_ENV_KEY")

    monkeypatch.setattr(probe, "inspect_runtime", fail)
    assert probe.main() == 1
    out = capsys.readouterr()
    assert out.out == "IMAGE_RUNTIME_CONTRACT_FAILED\n" and out.err == ""


def test_app_candidate_contract_before_switch_retains_baseline(session, capsys):  # noqa: F811
    deployment, fake, candidate = session("app")
    original = tree_hashes(deployment.state)

    def fail(args, timeout=120):
        if args[:2] == ["docker", "run"]:
            raise RuntimeError("FAKE_PRIVATE_TEXT_ENV_KEY")
        return fake(args, timeout)

    deployment.run = fail
    with pytest.raises(DeployError, match="IMAGE_RUNTIME_CONTRACT_FAILED"):
        deployment.update(candidate, "none", False)
    assert tree_hashes(deployment.state) == original
    assert not fake.ups and not (deployment.state / "pending.json").exists()
    assert "FAKE_PRIVATE_TEXT_ENV_KEY" not in capsys.readouterr().out


@pytest.mark.parametrize("failure", [True, False])
def test_web_prepare_checks_app_image_before_any_service(tmp_path, monkeypatch, failure, capsys):
    monkeypatch.setattr(acceptance, "ACCEPTANCE_ROOT", tmp_path / "sessions")
    source = tmp_path / "source"
    runtime_source(source)
    monkeypatch.setattr(acceptance, "verify_source", lambda p: {"files": tree_hashes(source)})
    root = acceptance.ACCEPTANCE_ROOT / "sl-accept-image20260904"
    deployment = Acceptance(
        root.name, root / "state", root / "evidence", "web", sleep=lambda _: None
    )

    class PrepareDocker(Docker):
        def __call__(self, args, timeout=120):
            if args[:2] == ["docker", "run"] and failure:
                self.calls.append(args)
                raise RuntimeError("FAKE_PRIVATE_TEXT_ENV_KEY")
            if "ls" in args or (args[:2] == ["docker", "compose"] and "up" in args):
                self.calls.append(args)
                return ""
            return super().__call__(args, timeout)

    fake = PrepareDocker(deployment)
    deployment.run = fake
    if failure:
        with pytest.raises(DeployError, match="IMAGE_RUNTIME_CONTRACT_FAILED"):
            deployment.prepare(source, None, False)
        assert not any("up" in c for c in fake.calls)
        assert not json.loads((deployment.state / "session.json").read_text())["ready"]
        assert list(deployment.evidence.glob("image-contract-failed-*.json"))
        assert "ACCEPTANCE_BASELINE_READY" not in capsys.readouterr().out
        with pytest.raises(DeployError, match="ACCEPTANCE_ALREADY_EXISTS"):
            deployment.prepare(source, None, False)
    else:
        assert deployment.prepare(source, None, False) == "ACCEPTANCE_BASELINE_READY"
        probe_index = next(i for i, c in enumerate(fake.calls) if c[:2] == ["docker", "run"])
        first_up = next(i for i, c in enumerate(fake.calls) if "up" in c)
        assert probe_index < first_up
        assert "IMAGE_RUNTIME_CONTRACT_OK" in capsys.readouterr().out
    assert not any("down" in c or "storylens-online" in c for c in fake.calls)


def test_existing_image_tag_refused_before_build(session):  # noqa: F811
    deployment, fake, candidate = session("app")

    def occupied(args, timeout=120):
        if args[:3] == ["docker", "image", "ls"]:
            return "occupied-image"
        return fake(args, timeout)

    deployment.run = occupied
    with pytest.raises(DeployError, match="ACCEPTANCE_IMAGE_ALREADY_EXISTS"):
        deployment.update(candidate, "none", False)
    assert not any("build" in c or "up" in c for c in fake.calls)
