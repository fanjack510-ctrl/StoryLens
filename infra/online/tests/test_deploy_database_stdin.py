"""R5: execute fingerprint SQL and exercise a real streamed shell, without Docker."""

import ast
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
import deploy_package
import deploy_runtime
import test_deploy_acceptance as acceptance_tests
from deploy_policy import DeployError


@pytest.fixture
def database_session(tmp_path, monkeypatch):
    make = acceptance_tests.session.__wrapped__(tmp_path, monkeypatch)
    model = ast.parse(
        (INFRA.parents[1] / "apps/online_api/storylens_online/db/models.py").read_text()
    )
    tables = {
        node.value.value
        for node in ast.walk(model)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets)
        and isinstance(node.value, ast.Constant)
    }
    assert "online_book_uploads" in tables and "online_uploads" not in tables
    databases = []

    def create(mode):
        deployment, fake, candidate = make(mode)
        db = sqlite3.connect(":memory:")
        databases.append(db)
        for table in tables:
            assert re.fullmatch(r"online_[a-z_]+", table)
            db.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
        queries = []

        def run(args, timeout=120):
            if "pg_dump" in args:
                return "\n".join(
                    r[0] for r in db.execute("SELECT sql FROM sqlite_master ORDER BY name")
                )
            if "psql" in args:
                sql = args[args.index("-c") + 1]
                queries.append(sql)
                names = re.findall(r"FROM\s+(\w+)", sql)
                assert set(names) == {
                    "online_analysis_jobs",
                    "online_book_uploads",
                    "online_model_usage_ledger",
                }
                assert set(names) <= tables and "online_uploads" not in sql
                return "|".join(str(value) for value in db.execute(sql).fetchone())
            return fake(args, timeout)

        deployment.run = run
        return deployment, fake, candidate, db, queries

    yield create
    for db in databases:
        db.close()


@pytest.mark.parametrize("mode", ["web", "app"])
def test_update_dry_run_executes_valid_database_query(database_session, mode):
    deployment, fake, candidate, db, queries = database_session(mode)
    before = {p.name: p.read_bytes() for p in deployment.state.iterdir()}
    assert deployment.update(candidate, "none", True) == "DRY_RUN_OK"
    assert queries and "online_book_uploads" in queries[0]
    with pytest.raises(sqlite3.OperationalError):
        db.execute(queries[0].replace("online_book_uploads", "online_uploads"))
    assert before == {p.name: p.read_bytes() for p in deployment.state.iterdir()}
    assert not list(deployment.evidence.iterdir())
    assert not any("up" in c or "build" in c for c in fake.calls)


@pytest.mark.parametrize("mode", ["web", "app"])
@pytest.mark.parametrize(
    "mutation",
    ["schema", "online_analysis_jobs", "online_book_uploads", "online_model_usage_ledger"],
)
def test_database_schema_and_row_count_changes_still_rejected(database_session, mode, mutation):
    deployment, fake, _, db, _ = database_session(mode)
    before = deployment.database_fingerprint()
    deployment.before_volumes = deployment.volume_identity()
    deployment.before_production = deployment.production_snapshot()
    if mutation == "schema":
        db.execute("ALTER TABLE online_book_uploads ADD COLUMN test_marker TEXT")
    else:
        db.execute(f'INSERT INTO "{mutation}" (id) VALUES (1)')
    with pytest.raises(DeployError, match="^DATABASE_CHANGED$"):
        deployment.verify_after(dict(fake.ids), before)
    assert fake.ids == fake.original


def test_all_deployment_subprocess_sites_detach_stdin():
    calls = []
    for path in INFRA.glob("deploy_*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
                and node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
            ):
                calls.append(path.name)
                keywords = {k.arg: k.value for k in node.keywords}
                assert ast.unparse(keywords["stdin"]) == "subprocess.DEVNULL"
    assert sorted(calls) == ["deploy_package.py", "deploy_runtime.py"]


@pytest.mark.parametrize("kind", ["success", "nonzero", "timeout", "encoding"])
def test_stdin_fix_preserves_capture_timeout_and_safe_errors(monkeypatch, capsys, kind):
    def run(args, **kwargs):
        assert kwargs == {
            "stdin": subprocess.DEVNULL,
            "capture_output": True,
            "check": False,
            "timeout": 7,
        }
        if kind == "timeout":
            raise subprocess.TimeoutExpired(args, 7, output=b"PRIVATE_TEST_OUTPUT")
        return subprocess.CompletedProcess(
            args,
            1 if kind == "nonzero" else 0,
            b"\xff" if kind == "encoding" else b"OK\n",
            b"PRIVATE_TEST_ERROR",
        )

    monkeypatch.setattr(subprocess, "run", run)
    if kind == "success":
        assert deploy_runtime.run_command(["docker", "info"], timeout=7) == "OK"
    else:
        with pytest.raises(DeployError, match="^COMMAND_FAILED_SAFELY$"):
            deploy_runtime.run_command(["docker", "info"], timeout=7)
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


def test_git_packaging_stdin_is_devnull(monkeypatch, tmp_path):
    def run(args, **kwargs):
        assert kwargs == {
            "stdin": subprocess.DEVNULL,
            "capture_output": True,
            "check": False,
            "timeout": 120,
        }
        return subprocess.CompletedProcess(args, 0, b"committed-bytes", b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert deploy_package.git(tmp_path, "rev-parse", "HEAD") == b"committed-bytes"


@pytest.mark.parametrize("legacy", [True, False])
def test_real_streamed_shell_retains_followup_commands(legacy):
    shell = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
    if not shell or not Path(shell).is_file():
        pytest.skip("bash unavailable for real streamed-shell regression")
    child = "import sys; print('STOLEN' if sys.stdin.read() else 'EMPTY')"
    command = [sys.executable, "-c", child]
    wrapper = (
        f"import sys,subprocess; sys.path.insert(0,{INFRA.as_posix()!r}); "
        "from deploy_runtime import run_command; print('WRAPPER_READY',flush=True); "
        + (
            f"print(subprocess.run({command!r},capture_output=True,check=True).stdout.decode(),flush=True)"
            if legacy
            else f"print(run_command({command!r}),flush=True)"
        )
    )
    first = "set -e\n" + shlex.join([Path(sys.executable).as_posix(), "-c", wrapper]) + "\n"
    # stdin is intentionally PIPE only for this outer, interactive test harness.
    process = subprocess.Popen(
        [shell, "-s"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        process.stdin.write(first)
        process.stdin.flush()
        assert process.stdout.readline().strip() == "WRAPPER_READY"
        process.stdin.write("printf '%s\\n' OUTER_STREAM_CONTINUED\n")
        process.stdin.close()
        process.stdin = None
        out, err = process.communicate(timeout=20)
        assert process.returncode == 0 and not err
        assert ("OUTER_STREAM_CONTINUED" in out) is not legacy
        assert ("STOLEN" in out) is legacy
        assert ("EMPTY" in out) is not legacy
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
