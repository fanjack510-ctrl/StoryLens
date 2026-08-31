from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "infra" / "online" / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / "infra" / "online" / ".env.example"
API_DOCKERFILE = REPO_ROOT / "infra" / "online" / "Dockerfile.api"
WORKER_ENTRYPOINT = REPO_ROOT / "infra" / "online" / "worker-entrypoint.sh"
PROVIDER_SECRET = "storylens_online_deepseek_api_key"
SOURCE_SECRET = f"/run/secrets/{PROVIDER_SECRET}"
STAGED_SECRET = "/run/storylens-online/deepseek-api-key"


def _shell_executable() -> str:
    candidates = (
        r"C:\Program Files\Git\usr\bin\sh.exe",
        r"C:\Program Files\Git\bin\bash.exe",
        shutil.which("sh"),
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    pytest.skip("a POSIX-compatible shell is required for entrypoint tests")


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _entrypoint_fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    source_secret = tmp_path / "source-secret"
    runtime_dir = tmp_path / "runtime"
    staged_secret = runtime_dir / "deepseek-api-key"
    entrypoint = tmp_path / "worker-entrypoint.sh"
    script = WORKER_ENTRYPOINT.read_text(encoding="utf-8")
    replacements = {
        f"SOURCE_SECRET={SOURCE_SECRET}": (
            f"SOURCE_SECRET={shlex.quote(source_secret.as_posix())}"
        ),
        "RUNTIME_DIR=/run/storylens-online": (f"RUNTIME_DIR={shlex.quote(runtime_dir.as_posix())}"),
        f"STAGED_SECRET={STAGED_SECRET}": (
            f"STAGED_SECRET={shlex.quote(staged_secret.as_posix())}"
        ),
        "STAGED_TEMP=/run/storylens-online/.deepseek-api-key.tmp": (
            f"STAGED_TEMP={shlex.quote((runtime_dir / '.deepseek-api-key.tmp').as_posix())}"
        ),
    }
    for before, after in replacements.items():
        assert before in script
        script = script.replace(before, after, 1)
    _write_executable(entrypoint, script)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    install_log = tmp_path / "install.log"
    chown_log = tmp_path / "chown.log"
    chmod_log = tmp_path / "chmod.log"
    gosu_log = tmp_path / "gosu.log"
    worker_log = tmp_path / "worker.log"

    _write_executable(
        fake_bin / "install",
        """#!/bin/sh
destination=
for item in "$@"; do destination=$item; done
printf '%s\\n' "$*" >> "$FAKE_INSTALL_LOG"
[ "${FAKE_FAIL_STEP:-}" = install ] && exit 7
mkdir -p "$destination"
/usr/bin/chmod 0700 "$destination"
""",
    )
    _write_executable(
        fake_bin / "chown",
        """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_CHOWN_LOG"
[ "${FAKE_FAIL_STEP:-}" = chown ] && exit 7
exit 0
""",
    )
    _write_executable(
        fake_bin / "chmod",
        """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_CHMOD_LOG"
[ "${FAKE_FAIL_STEP:-}" = chmod ] && exit 7
exec /usr/bin/chmod "$@"
""",
    )
    _write_executable(
        fake_bin / "mv",
        """#!/bin/sh
[ "${FAKE_FAIL_STEP:-}" = mv ] && exit 7
exec /usr/bin/mv "$@"
""",
    )
    _write_executable(
        fake_bin / "gosu",
        """#!/bin/sh
identity=$1
shift
printf '%s\\n' "$identity" >> "$FAKE_GOSU_LOG"
[ "${FAKE_FAIL_STEP:-}" = gosu ] && exit 7
if [ "$#" -eq 1 ] && [ "$1" = true ]; then exit 0; fi
export FAKE_EFFECTIVE_IDENTITY="$identity"
exec "$@"
""",
    )
    fake_worker = tmp_path / "fake-worker.sh"
    _write_executable(
        fake_worker,
        """#!/bin/sh
printf '%s\\n' "$FAKE_EFFECTIVE_IDENTITY" > "$FAKE_WORKER_LOG"
""",
    )

    environment = os.environ.copy()
    git_usr_bin = Path(r"C:\Program Files\Git\usr\bin")
    path_parts = [str(fake_bin)]
    if git_usr_bin.is_dir():
        path_parts.append(str(git_usr_bin))
    path_parts.append(environment.get("PATH", ""))
    environment.update(
        {
            "PATH": os.pathsep.join(path_parts),
            "FAKE_INSTALL_LOG": install_log.as_posix(),
            "FAKE_CHOWN_LOG": chown_log.as_posix(),
            "FAKE_CHMOD_LOG": chmod_log.as_posix(),
            "FAKE_GOSU_LOG": gosu_log.as_posix(),
            "FAKE_WORKER_LOG": worker_log.as_posix(),
        }
    )
    logs = {
        "install": install_log.as_posix(),
        "chown": chown_log.as_posix(),
        "chmod": chmod_log.as_posix(),
        "gosu": gosu_log.as_posix(),
        "worker": worker_log.as_posix(),
        "worker_command": fake_worker.as_posix(),
    }
    return entrypoint, source_secret, staged_secret, environment | logs


def _run_entrypoint(
    entrypoint: Path,
    environment: dict[str, str],
    *,
    enabled: bool,
) -> subprocess.CompletedProcess[str]:
    run_environment = environment.copy()
    run_environment["STORYLENS_ONLINE_PHASE2B1_ENABLED"] = "true" if enabled else "false"
    return subprocess.run(
        [_shell_executable(), entrypoint.as_posix(), environment["worker_command"]],
        cwd=entrypoint.parent,
        env=run_environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_provider_secret_is_mounted_only_into_worker() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["online-worker"]["secrets"] == [
        {"source": PROVIDER_SECRET, "target": PROVIDER_SECRET}
    ]
    for service_name, service in services.items():
        if service_name != "online-worker":
            mounted = service.get("secrets", [])
            assert PROVIDER_SECRET not in mounted
            assert all(
                not isinstance(item, dict) or item.get("source") != PROVIDER_SECRET
                for item in mounted
            )

    worker_environment = services["online-worker"]["environment"]
    assert worker_environment["STORYLENS_ONLINE_PHASE2B1_API_KEY_FILE"] == STAGED_SECRET
    for service in services.values():
        environment_text = str(service.get("environment", {})).lower()
        assert "phase2b1_api_key=" not in environment_text
        assert "bearer " not in environment_text


def test_worker_alone_uses_root_staging_wrapper_and_restricted_tmpfs() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]
    worker = services["online-worker"]

    assert worker["user"] == "0:0"
    assert worker["entrypoint"] == ["/usr/local/bin/storylens-online-worker-entrypoint"]
    assert worker["tmpfs"] == ["/run/storylens-online:rw,noexec,nosuid,nodev,size=64k,mode=0700"]
    assert SOURCE_SECRET not in str(worker["environment"])
    assert SOURCE_SECRET not in str(worker["command"])
    assert SOURCE_SECRET not in str(worker["entrypoint"])

    api = services["online-api"]
    assert "user" not in api
    assert "entrypoint" not in api
    assert "tmpfs" not in api

    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    assert "gosu" in dockerfile
    assert "USER storylens" in dockerfile
    assert dockerfile.index("USER storylens") < dockerfile.index("CMD [")


def test_worker_entrypoint_has_lf_executable_and_fixed_safety_controls() -> None:
    contents = WORKER_ENTRYPOINT.read_bytes()
    script = contents.decode("utf-8")
    index_entry = subprocess.run(
        ["git", "ls-files", "--stage", WORKER_ENTRYPOINT.relative_to(REPO_ROOT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert b"\r" not in contents
    assert index_entry.startswith("100755 ")
    assert "umask 077" in script
    assert "install -d -m 0700 -o 0 -g 0" in script
    assert 'chmod 0400 "$STAGED_TEMP"' in script
    assert 'chmod 0700 "$RUNTIME_DIR"' in script
    assert "APP_IDENTITY=10001:10001" in script
    assert 'exec "$runner" "$APP_IDENTITY" "$@"' in script
    assert "Worker secret initialization failed safely." in script
    assert "set -x" not in script


def test_disabled_feature_does_not_read_or_stage_secret(tmp_path: Path) -> None:
    entrypoint, source, staged, environment = _entrypoint_fixture(tmp_path)
    assert not source.exists()

    result = _run_entrypoint(entrypoint, environment, enabled=False)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not staged.parent.exists()
    assert Path(environment["worker"]).read_text(encoding="utf-8").strip() == ("10001:10001")
    assert Path(environment["install"]).exists() is False
    assert Path(environment["chown"]).exists() is False


def test_enabled_feature_stages_exact_bytes_and_drops_privileges(tmp_path: Path) -> None:
    entrypoint, source, staged, environment = _entrypoint_fixture(tmp_path)
    fake_secret = b"sk-TESTONLY_1234567890abcdef"
    source.write_bytes(fake_secret)

    result = _run_entrypoint(entrypoint, environment, enabled=True)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert staged.read_bytes() == fake_secret
    assert fake_secret.decode() not in result.stdout + result.stderr
    assert "10001:10001" in Path(environment["chown"]).read_text(encoding="utf-8")
    chmod_log = Path(environment["chmod"]).read_text(encoding="utf-8")
    assert "0400" in chmod_log
    assert "0700" in chmod_log
    assert Path(environment["worker"]).read_text(encoding="utf-8").strip() == ("10001:10001")
    gosu_calls = Path(environment["gosu"]).read_text(encoding="utf-8").splitlines()
    assert gosu_calls == ["10001:10001", "10001:10001"]


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("missing", None),
        ("empty", b""),
        ("invalid", b"not-a-deepseek-key"),
        ("multiline", b"sk-TESTONLY_1234567890abcdef\nsecond"),
        ("carriage_return", b"sk-TESTONLY_1234567890abcdef\r"),
        ("space", b"sk-TESTONLY_1234567890abc def"),
        ("nul", b"sk-TESTONLY_1234567890abcdef\x00"),
        ("directory", None),
    ],
)
def test_invalid_secret_fails_closed_with_fixed_safe_log(
    tmp_path: Path,
    kind: str,
    payload: bytes | None,
) -> None:
    entrypoint, source, staged, environment = _entrypoint_fixture(tmp_path)
    if kind == "directory":
        source.mkdir()
    elif payload is not None:
        source.write_bytes(payload)

    result = _run_entrypoint(entrypoint, environment, enabled=True)

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "Worker secret initialization failed safely.\n"
    assert not staged.exists()
    assert not Path(environment["worker"]).exists()
    if payload:
        assert payload.decode("utf-8", errors="ignore") not in result.stderr


@pytest.mark.parametrize("failure_step", ["install", "chown", "chmod", "mv", "gosu"])
def test_staging_or_privilege_drop_failure_is_fixed_and_secret_safe(
    tmp_path: Path,
    failure_step: str,
) -> None:
    entrypoint, source, _staged, environment = _entrypoint_fixture(tmp_path)
    fake_secret = b"sk-TESTONLY_1234567890abcdef"
    source.write_bytes(fake_secret)
    environment["FAKE_FAIL_STEP"] = failure_step

    result = _run_entrypoint(entrypoint, environment, enabled=True)

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "Worker secret initialization failed safely.\n"
    assert fake_secret.decode() not in result.stdout + result.stderr
    assert not Path(environment["worker"]).exists()


def test_only_worker_network_boundary_changes_for_provider_egress() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["online-worker"]["networks"] == ["private", "egress"]
    assert services["online-api"]["networks"] == ["private", "egress"]
    assert services["online-web"]["networks"] == ["private"]
    assert services["gateway"]["networks"] == ["edge", "private"]
    assert services["pocketbase"]["networks"] == ["private", "egress"]
    assert services["pocketbase-init"]["network_mode"] == "none"
    assert "ports" not in services["online-worker"]


def test_api_receives_only_gate_allowlist_and_limits() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    api_environment = compose["services"]["online-api"]["environment"]
    worker_environment = compose["services"]["online-worker"]["environment"]

    assert "STORYLENS_ONLINE_PHASE2B1_ENABLED" in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_ALLOWLISTED_USER_IDS_CSV" in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_TEXT_MAX_BYTES" in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_BASE_URL" not in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_API_KEY_FILE" not in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_PRICING_VERSION" not in api_environment

    assert worker_environment["STORYLENS_ONLINE_PHASE2B1_BASE_URL"] == ("https://api.deepseek.com")
    assert "STORYLENS_ONLINE_PHASE2B1_API_KEY_FILE" in worker_environment
    assert "STORYLENS_ONLINE_PHASE2B1_PRICING_VERSION" not in worker_environment


def test_secret_value_is_absent_from_tracked_configuration_and_image() -> None:
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "PHASE2B1_API_KEY=" not in env_example
    assert "PHASE2B1_API_KEY_FILE=" in env_example
    assert "FAKE_PHASE2B1_KEY" not in env_example
    assert "API_KEY" not in dockerfile
    assert "ARG STORYLENS_ONLINE_PHASE2B1" not in dockerfile
    assert "Authorization" not in compose


def test_superseded_provider_has_no_runtime_test_or_deployment_reference() -> None:
    roots = (
        REPO_ROOT / "apps" / "online_api",
        REPO_ROOT / "apps" / "online_web" / "src",
        REPO_ROOT / "infra" / "online",
        REPO_ROOT / "docs" / "online",
    )
    banned = ("ali" + "yun", "bai" + "lian", "qw" + "en")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".yml", ".yaml", ".md", ".example"}:
                continue
            lowered = path.read_text(encoding="utf-8").lower()
            assert not any(marker in lowered for marker in banned), path
