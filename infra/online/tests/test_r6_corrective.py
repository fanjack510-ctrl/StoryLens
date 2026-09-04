import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest
import r6_gate as gate
import test_deploy_acceptance as acceptance_tests
from test_deploy_acceptance import INFRA, runtime_source
from test_deploy_image_contract import (
    test_context_defects_fail_closed as context_defect,
)
from test_deploy_image_contract import (
    test_existing_image_tag_refused_before_build as occupied_tag,
)
from test_deploy_image_contract import (
    test_source_present_image_contract_failure_is_safe as image_defect,
)


@pytest.fixture
def public_context_trust(monkeypatch):
    import deploy_acceptance as acceptance
    import deploy_image_contract as contract

    # Direct calls to imported test functions do not run their module fixtures.
    # Patch each lookup site; /tmp ancestor ownership is outside these tests.
    acceptance_calls, contract_calls = [], []
    monkeypatch.setattr(acceptance, "trusted", acceptance_calls.append)
    monkeypatch.setattr(contract, "trusted", contract_calls.append)
    return acceptance_calls, contract_calls


def test_tree_hashes_uses_patched_defining_module(tmp_path, monkeypatch, public_context_trust):
    import deploy_acceptance as acceptance
    import deploy_image_contract as contract
    import deploy_protocol as protocol
    from deploy_acceptance import tree_hashes

    original = protocol.trusted
    source = tmp_path / "public-source"
    runtime_source(source)
    acceptance_calls, contract_calls = public_context_trust
    assert tree_hashes.__globals__["trusted"] is acceptance.trusted
    assert contract.context_contract.__globals__["trusted"] is contract.trusted
    assert acceptance.trusted != contract.trusted

    # A same-named patch in contract alone cannot intercept tree_hashes.
    def reject(_):
        raise ValueError("UNTRUSTED_PATH")

    with monkeypatch.context() as control:
        control.setattr(acceptance, "trusted", reject)
        with pytest.raises(ValueError, match="^UNTRUSTED_PATH$"):
            tree_hashes(source)
    assert not acceptance_calls and not contract_calls
    manifest = tree_hashes(source)
    assert set(acceptance_calls) == set(source.rglob("*"))
    assert not contract_calls
    contract.context_contract(source, manifest)
    assert set(contract_calls) == set(source.rglob("*"))
    assert protocol.trusted is original  # production guard itself stays intact


def test_occupied_tag_not_masked_under077(tmp_path, monkeypatch):
    make = acceptance_tests.session.__wrapped__(tmp_path, monkeypatch)
    old = os.umask(0o077)
    try:
        occupied_tag(make)
    finally:
        os.umask(old)


@pytest.mark.parametrize("name", ["ACCEPTANCE.md", "R6-H-ONLY.md"])
def test_acceptance_bash_blocks_parse_without_execution(name):
    shell = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
    assert shell
    blocks = re.findall(
        r"```bash\n(.*?)\n```", (INFRA / name).read_text(encoding="utf-8"), re.DOTALL
    )
    assert blocks
    if name == "R6-H-ONLY.md":
        # bash -n on a heredoc caller does not parse the script sent on stdin.
        assert len(blocks) == 1
        body = blocks[0].split("<<'R7_ACCEPTANCE'\n", 1)[1].rsplit("\nR7_ACCEPTANCE", 1)[0]
        paths = [
            '"$SOURCE/infra/online/tests/test_r6_corrective.py"',
            '"$SOURCE/infra/online/tests"',
            '"$SOURCE/infra/online/tests/test_deploy_secret_boundary.py"',
            '"$SOURCE/infra/online/tests/test_deploy_database_stdin.py"',
        ]
        positions = [body.index(path) for path in paths]
        assert positions == sorted(positions)
        commands = [line for line in body.splitlines() if " -m pytest " in line]
        assert len(commands) == 4
        assert all(line.startswith("(umask 022; ") and ') > "$AUDIT/' in line for line in commands)
        assert 'test "$(umask)" = 0077' in body
        assert "50 passed" in body and "18 passed" in body and "1 passed" in body
        blocks.append(body)
    for block in blocks:
        result = subprocess.run(
            [shell, "-n", "-c", block], stdin=subprocess.DEVNULL, capture_output=True, check=False
        )
        assert result.returncode == 0


def test_fixture_under_parent077_preserves_umask_and_private_ancestors(
    tmp_path, public_context_trust
):
    import deploy_image_contract as contract
    from deploy_acceptance import tree_hashes

    before = stat.S_IMODE(tmp_path.stat().st_mode)
    old = os.umask(0o077)
    try:
        source = tmp_path / "public-source"
        runtime_source(source)
        contract.context_contract(source, tree_hashes(source))
        if os.name == "posix":
            assert os.umask(0o077) == 0o077
        assert stat.S_IMODE(tmp_path.stat().st_mode) == before
        if os.name == "posix":
            for path in [source, *source.rglob("*")]:
                expected = 0o755 if path.is_dir() else (0o555 if path.suffix == ".sh" else 0o644)
                assert stat.S_IMODE(path.stat().st_mode) == expected
    finally:
        os.umask(old)


@pytest.mark.parametrize("defect", ["missing", "hash", "namespace", "error"])
def test_image_error_not_masked_under077(tmp_path, public_context_trust, defect):
    old = os.umask(0o077)
    try:
        image_defect(tmp_path, defect)
        if os.name == "posix":
            assert os.umask(0o077) == 0o077
    finally:
        os.umask(old)


@pytest.mark.parametrize("defect", ["missing", "hash", "namespace", "empty_dir", "ignore"])
def test_context_errors_still_rejected_under077(tmp_path, public_context_trust, defect):
    old = os.umask(0o077)
    try:
        context_defect(tmp_path, defect)
    finally:
        os.umask(old)


def baseline():
    files = {
        "infra/online/" + n: ((INFRA / n).read_bytes(), 0o755 if n.endswith(".sh") else 0o644)
        for n in gate.TOOLS
    }
    files.update(
        {
            "VERSION": (b"1.3.6\n", 0o644),
            "apps/online_web/index.html": (b"<head></head>", 0o644),
            "apps/online_api/storylens_online/errors.py": (b"# stub", 0o644),
            "infra/online/worker-entrypoint.sh": (b"#!/bin/sh\n", 0o755),
        }
    )
    for name in ("init_schema.py", "models.py", "phase2b1_migration.py"):
        files["apps/online_api/storylens_online/db/" + name] = (b"# stub", 0o644)
    return files


@pytest.mark.parametrize(
    "path",
    [
        "apps/online_api/requirements.txt",
        "apps/online_web/package-lock.json",
        "infra/online/deploy_runtime.py",
        "infra/online/Dockerfile.api",
        "infra/online/worker-entrypoint.sh",
        "infra/online/docker-compose.yml",
        "infra/online/pocketbase/pb_migrations/new.js",
        ".dockerignore",
        "unknown-input",
    ],
)
def test_changed_new_deleted_build_inputs_refuse_equivalence(path):
    old = baseline()
    new = dict(old)
    new[path] = (b"changed", 0o644)
    with pytest.raises(ValueError, match="FULL_ACCEPTANCE_REQUIRED"):
        gate.equivalent(old, new)
    with pytest.raises(ValueError):
        gate.equivalent(new, old)


def test_only_tests_docs_registration_change_and_tool_fingerprint_constant():
    from deploy_protocol import TOOL_FILES, tool_version

    old, new = baseline(), baseline()
    new["infra/online/tests/test_new.py"] = (b"# test", 0o644)
    new["infra/online/ACCEPTANCE.md"] = (b"# instructions", 0o644)
    assert gate.equivalent(old, new)
    assert tuple(TOOL_FILES) == gate.TOOLS and tool_version(INFRA) == gate.TV
    new["infra/online/deploy_runtime.py"] = (new["infra/online/deploy_runtime.py"][0], 0o777)
    with pytest.raises(ValueError):
        gate.equivalent(old, new)


def test_archive_checks_external_hash_internal_hash_protocol_and_paths(tmp_path):
    files = baseline()
    meta = {
        "commit": gate.R5,
        "protocol": 2,
        "tool_version": gate.TV,
        "files": {n: gate.sha(v[0]) for n, v in files.items()},
    }

    def pack():
        path = tmp_path / "test.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            for name, (data, mode) in {
                **files,
                "bootstrap.json": (json.dumps(meta).encode(), 0o644),
            }.items():
                item = tarfile.TarInfo(name)
                item.size, item.mode = len(data), mode
                tar.addfile(item, io.BytesIO(data))
        return path, gate.sha(path.read_bytes())

    path, digest = pack()
    assert gate.archive(path, digest)[1] == meta
    with pytest.raises(ValueError):
        gate.archive(path, "0" * 64)
    meta["protocol"] = 999
    with pytest.raises(ValueError):
        gate.archive(*pack())
    meta["protocol"] = 2
    meta["files"]["VERSION"] = "0" * 64
    with pytest.raises(ValueError):
        gate.archive(*pack())
    meta["files"]["VERSION"] = gate.sha(files["VERSION"][0])
    files["../escape"] = (b"unsafe", 0o644)
    with pytest.raises(ValueError):
        gate.archive(*pack())


@pytest.fixture
def evidence_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "private", lambda *_: None)  # OS checks tested separately
    files = baseline()
    manifests = {n: gate.sha(v[0]) for n, v in files.items()}
    root = tmp_path / "sessions"
    locks = tmp_path / "locks"
    locks.mkdir()
    for project, (mode, status) in gate.PROJECTS.items():
        (locks / (project + ".lock")).touch()
        state, ev = root / project / "state", root / project / "evidence"
        state.mkdir(parents=True)
        ev.mkdir()
        candidate = dict(manifests)
        name = (
            "apps/online_web/index.html"
            if mode == "web"
            else "apps/online_api/storylens_online/errors.py"
        )
        content = files[name][0]
        content = (
            content.replace(
                b"</head>", b'<meta name="storylens-acceptance" content="candidate-v2"></head>'
            )
            if mode == "web"
            else content
            + b"\n# Isolated deployment acceptance candidate v2; no business changes.\n"
        )
        candidate[name] = gate.sha(content)
        record = {
            "mode": mode,
            "project": project,
            "ready": True,
            "baseline": manifests,
            "candidates": {mode: candidate},
        }
        (state / "session.json").write_text(json.dumps(record))
        before = {n: gate.sha(n.encode()) for n in gate.SERVICES}
        targets = {"online-web"} if mode == "web" else {"online-api", "online-worker"}
        after = {n: gate.sha((n + "after").encode()) if n in targets else before[n] for n in before}
        records = {
            "1.json": {
                "status": status,
                "mode": mode,
                "project": project,
                "database_unchanged": True,
                "before": before,
                "after": after,
            },
            "image-contract-1.json": {
                "status": "IMAGE_RUNTIME_CONTRACT_OK",
                "image": "sha256:" + "a" * 64,
                "entrypoint": manifests["infra/online/worker-entrypoint.sh"],
                "files": {
                    n.removeprefix("apps/online_api/storylens_online/"): h
                    for n, h in manifests.items()
                    if n.startswith("apps/online_api/storylens_online/")
                },
            },
            "secret-boundary-1.json": {
                "status": "SECRET_BOUNDARY_OK",
                "mode": mode,
                "project": project,
            },
        }
        if mode == "app":
            extra = json.loads(json.dumps(records["image-contract-1.json"]))
            extra["files"]["errors.py"] = candidate["apps/online_api/storylens_online/errors.py"]
            extra["image"] = "sha256:" + "b" * 64
            records["image-contract-2.json"] = extra
        for name, record in records.items():
            (ev / name).write_text(json.dumps(record))

    def call(args):
        for project in gate.PROJECTS:
            data = json.loads((root / project / "evidence/1.json").read_text())
            for name, identifier in data["after"].items():
                if args[-1] == identifier:
                    # Projects deliberately use disjoint IDs in real fixtures below.
                    return project + " " + name
        raise AssertionError("unexpected command")

    # Make fixture IDs unique per project.
    for project in gate.PROJECTS:
        path = root / project / "evidence/1.json"
        record = json.loads(path.read_text())
        for side in ("before", "after"):
            record[side] = {n: gate.sha((project + v).encode()) for n, v in record[side].items()}
        path.write_text(json.dumps(record))
    return root, tmp_path / "locks", files, call


def test_four_r5_evidence_sets_linked_read_only(evidence_tree):
    assert len(gate.evidence(*evidence_tree)) == 22


@pytest.mark.parametrize(
    "defect",
    ["database", "missing", "ready", "pending", "baseline", "secret", "image", "unrelated"],
)
def test_bad_or_incomplete_r5_evidence_requires_full_acceptance(evidence_tree, defect):
    root, *_ = evidence_tree
    project = next(iter(gate.PROJECTS))
    state, ev = root / project / "state", root / project / "evidence"
    if defect == "missing":
        (ev / "1.json").unlink()
    elif defect == "pending":
        (state / "pending.json").write_text("{}")
    else:
        path = (
            state / "session.json"
            if defect in {"ready", "baseline"}
            else ev
            / (
                "secret-boundary-1.json"
                if defect == "secret"
                else "image-contract-1.json"
                if defect == "image"
                else "1.json"
            )
        )
        record = json.loads(path.read_text())
        if defect == "ready":
            record["ready"] = False
        if defect == "baseline":
            record["baseline"]["VERSION"] = "0" * 64
        if defect == "database":
            record["database_unchanged"] = False
        if defect == "secret":
            record["status"] = "SECRET_BOUNDARY_FAILED"
        if defect == "image":
            record["files"].pop("db/models.py")
        if defect == "unrelated":
            record["after"]["redis"] = "f" * 64
        path.write_text(json.dumps(record))
    with pytest.raises((ValueError, KeyError)):
        gate.evidence(*evidence_tree)


def test_gate_subprocess_stdin_fixed_errors(monkeypatch):
    def fake(args, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["capture_output"]
        assert args[:3] == ["docker", "--host", "unix:///var/run/docker.sock"]
        return subprocess.CompletedProcess(args, 1, "PRIVATE_SENTINEL", "PRIVATE_SENTINEL")

    monkeypatch.setattr(gate.subprocess, "run", fake)
    with pytest.raises(ValueError, match="^R6_GATE_FAILED_FULL_ACCEPTANCE_REQUIRED$"):
        gate.run(["ps"])


@pytest.mark.parametrize(
    "defect", ["none", "container", "image", "restart", "volume", "recreated", "current"]
)
def test_production_r5_snapshot_comparison_is_read_only(tmp_path, monkeypatch, defect):
    monkeypatch.setattr(gate, "private", lambda *_: None)
    identifier, image = "a" * 64, "sha256:" + "b" * 64
    (tmp_path / "images-before.txt").write_text(f"{identifier} {image} 0\n")
    (tmp_path / "volumes-before.txt").write_text("storylens-online_postgres_data\n")
    monkeypatch.setattr(
        gate.os,
        "readlink",
        lambda _: "/opt/storylens/releases/" + ("unknown" if defect == "current" else "4ae7f663"),
    )

    def call(args):
        assert not any(n in args for n in ("up", "down", "exec", "build", "rm"))
        if args[0] == "ps":
            return identifier
        if args[0] == "inspect":
            return " ".join(
                (
                    "c" * 64 if defect == "container" else identifier,
                    "sha256:" + "d" * 64 if defect == "image" else image,
                    "1" if defect == "restart" else "0",
                )
            )
        if args[:2] == ["volume", "ls"]:
            return (
                "storylens-online_new" if defect == "volume" else "storylens-online_postgres_data"
            )
        assert args[:2] == ["volume", "inspect"]
        return "2999-01-01T00:00:00Z" if defect == "recreated" else "2020-01-01T00:00:00Z"

    if defect == "none":
        assert gate.production(tmp_path, call)
    else:
        with pytest.raises(ValueError):
            gate.production(tmp_path, call)


@pytest.mark.parametrize(
    "mode,uid,gid,links",
    [
        (stat.S_IFREG | 0o644, 0, 0, 1),
        (stat.S_IFLNK | 0o600, 0, 0, 1),
        (stat.S_IFREG | 0o600, 10001, 0, 1),
        (stat.S_IFREG | 0o600, 0, 10001, 1),
        (stat.S_IFREG | 0o600, 0, 0, 2),
        (stat.S_IFIFO | 0o600, 0, 0, 1),
    ],
)
def test_gate_private_evidence_and_lock_attributes(mode, uid, gid, links):
    from types import SimpleNamespace

    fake = SimpleNamespace(
        lstat=lambda: SimpleNamespace(st_mode=mode, st_uid=uid, st_gid=gid, st_nlink=links),
        parents=(),
    )
    with pytest.raises(ValueError):
        gate.private(fake)


def test_gate_root_sticky_lock_parent_does_not_weaken_private_leaf(monkeypatch):
    from types import SimpleNamespace

    path = Path("/run/lock/storylens-online-deploy/project.lock")

    def info(p):
        mode = (
            stat.S_IFREG | 0o600
            if p == path
            else stat.S_IFDIR | (0o1777 if p == Path("/run/lock") else 0o700)
        )
        return SimpleNamespace(st_mode=mode, st_uid=0, st_gid=0, st_nlink=1)

    monkeypatch.setattr(Path, "lstat", info)
    gate.private(path)


def test_h_commands_local_umask_and_shell_permissions(tmp_path):
    doc = (INFRA / "ACCEPTANCE.md").read_text(encoding="utf-8")
    commands = [line for line in doc.splitlines() if " -m pytest " in line and "$SOURCE" in line]
    assert len(commands) >= 3
    assert all(line.startswith("(umask 022; ") and ') > "$AUDIT/' in line for line in commands)
    shell = shutil.which("bash")
    if os.name == "nt":
        shell = "C:/Program Files/Git/bin/bash.exe"
    assert shell  # do not silently skip the umask boundary regression
    result = subprocess.run(
        [
            shell,
            "-c",
            (
                "umask 077; before=$(umask); (umask 022; true) > log; "
                'test "$(umask)" = "$before"; test "$(stat -c %a log)" = 600'
            ),
        ],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    # Windows ACL-backed stat does not model POSIX mode. The shell mask still must match.
    if os.name == "posix":
        assert result.returncode == 0
    else:
        result = subprocess.run(
            [shell, "-c", 'umask 077; (umask 022; true); test "$(umask)" = 0077'],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
