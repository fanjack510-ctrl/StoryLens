from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_DIR = REPO_ROOT / "infra" / "online"
COMPOSE_FILE = INFRA_DIR / "docker-compose.yml"
INIT_SCRIPT = INFRA_DIR / "pocketbase" / "init-superuser.sh"
POCKETBASE_DOCKERFILE = INFRA_DIR / "pocketbase" / "Dockerfile"
CADDYFILE = INFRA_DIR / "Caddyfile"

FAKE_EMAIL = "bootstrap-test@example.invalid"
FAKE_PASSWORD = "FAKE_ONLY_32_CHAR_PASSWORD_123456789"
ROTATED_FAKE_PASSWORD = "FAKE_ONLY_ROTATED_PASSWORD_987654321"


def _shell_executable() -> str:
    candidates = [
        Path(r"C:\Program Files\Git\usr\bin\sh.exe"),
        Path(r"C:\Program Files\Git\bin\bash.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    executable = shutil.which("sh")
    if executable is None:
        pytest.skip("POSIX shell is not available for the bootstrap script test")
    return executable


def _write_fake_pocketbase(tmp_path: Path) -> Path:
    fake_binary = tmp_path / "fake-pocketbase.sh"
    fake_binary.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' 'http://127.0.0.1:8090/_/#/pbinstall/eyJFAKEJWT' >&1
printf '%s\\n' 'FAKE_CLI_OUTPUT_MUST_BE_SUPPRESSED' >&2
if [ "${FAKE_PB_FAIL:-0}" = "1" ]; then
    exit 7
fi
if [ "$1" = "migrate" ] && [ "$2" = "up" ]; then
    printf '%s\\n' 'migrate up' >> "$FAKE_CALL_LOG"
    exit 0
fi
if [ "$1" = "superuser" ] && [ "$2" = "upsert" ]; then
    [ "$3" = "$EXPECTED_EMAIL" ] || exit 8
    [ "$4" = "$EXPECTED_PASSWORD" ] || exit 9
    printf '%s\\n' 'superuser upsert' >> "$FAKE_CALL_LOG"
    exit 0
fi
exit 10
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_binary.chmod(0o755)
    return fake_binary


def _run_init(
    tmp_path: Path,
    *,
    email: str | None = FAKE_EMAIL,
    password: str | None = FAKE_PASSWORD,
    fail_cli: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_binary = _write_fake_pocketbase(tmp_path)
    email_file = tmp_path / "email.secret"
    password_file = tmp_path / "password.secret"
    call_log = tmp_path / "calls.log"
    data_dir = tmp_path / "pb_data"
    migration_dir = tmp_path / "pb_migrations"
    data_dir.mkdir(exist_ok=True)
    migration_dir.mkdir(exist_ok=True)
    if email is not None:
        email_file.write_text(email + "\r\n", encoding="utf-8", newline="")
    if password is not None:
        password_file.write_text(password + "\r\n", encoding="utf-8", newline="")

    environment = os.environ.copy()
    shell = _shell_executable()
    git_usr_bin = Path(r"C:\Program Files\Git\usr\bin")
    if git_usr_bin.is_dir():
        environment["PATH"] = os.pathsep.join([str(git_usr_bin), environment.get("PATH", "")])
    environment.update(
        {
            "POCKETBASE_BINARY": fake_binary.as_posix(),
            "POCKETBASE_DATA_DIR": data_dir.as_posix(),
            "POCKETBASE_MIGRATIONS_DIR": migration_dir.as_posix(),
            "POCKETBASE_SUPERUSER_EMAIL_FILE": email_file.as_posix(),
            "POCKETBASE_SUPERUSER_PASSWORD_FILE": password_file.as_posix(),
            "POCKETBASE_RUNNER": "",
            "EXPECTED_EMAIL": email or "",
            "EXPECTED_PASSWORD": password or "",
            "FAKE_CALL_LOG": call_log.as_posix(),
            "FAKE_PB_FAIL": "1" if fail_cli else "0",
        }
    )
    result = subprocess.run(
        [shell, INIT_SCRIPT.as_posix()],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        timeout=10,
    )
    return result, call_log


@pytest.mark.parametrize("missing", ["email", "password"])
def test_init_fails_closed_when_a_secret_file_is_missing(tmp_path: Path, missing: str) -> None:
    result, call_log = _run_init(
        tmp_path,
        email=None if missing == "email" else FAKE_EMAIL,
        password=None if missing == "password" else FAKE_PASSWORD,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "PocketBase initialization failed safely.\n"
    assert not call_log.exists()


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("", FAKE_PASSWORD),
        (FAKE_EMAIL, ""),
        ("not-an-email", FAKE_PASSWORD),
        (FAKE_EMAIL, "short"),
        (FAKE_EMAIL + "\nsecond@example.invalid", FAKE_PASSWORD),
        (FAKE_EMAIL, FAKE_PASSWORD + "\nsecond-line"),
    ],
    ids=[
        "empty-email",
        "empty-password",
        "invalid-email",
        "short-password",
        "multiline-email",
        "multiline-password",
    ],
)
def test_init_rejects_empty_or_invalid_secret_content(
    tmp_path: Path,
    email: str,
    password: str,
) -> None:
    result, call_log = _run_init(tmp_path, email=email, password=password)

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "PocketBase initialization failed safely.\n"
    assert not call_log.exists()


def test_init_preserves_secret_characters_and_emits_only_fixed_success_log(
    tmp_path: Path,
) -> None:
    special_password = ROTATED_FAKE_PASSWORD + " $'\\\""
    result, call_log = _run_init(tmp_path, password=special_password)

    assert result.returncode == 0
    assert result.stdout == "PocketBase initialization completed safely.\n"
    assert result.stderr == ""
    combined_output = (result.stdout + result.stderr).lower()
    for forbidden in (
        FAKE_EMAIL.lower(),
        special_password.lower(),
        "pbinstall",
        "eyj",
        "http://",
        "fake_cli_output",
    ):
        assert forbidden not in combined_output
    assert call_log.read_text(encoding="utf-8").splitlines() == [
        "migrate up",
        "superuser upsert",
    ]


def test_init_cli_failure_is_nonzero_and_does_not_leak_inputs(tmp_path: Path) -> None:
    result, call_log = _run_init(tmp_path, fail_cli=True)

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "PocketBase initialization failed safely.\n"
    combined_output = (result.stdout + result.stderr).lower()
    assert FAKE_EMAIL.lower() not in combined_output
    assert FAKE_PASSWORD.lower() not in combined_output
    assert "pbinstall" not in combined_output
    assert "eyj" not in combined_output
    assert not call_log.exists()


def test_init_is_repeatable_and_accepts_password_rotation(tmp_path: Path) -> None:
    first, call_log = _run_init(tmp_path)
    second, call_log = _run_init(tmp_path, password=ROTATED_FAKE_PASSWORD)

    assert first.returncode == 0
    assert second.returncode == 0
    assert call_log.read_text(encoding="utf-8").splitlines() == [
        "migrate up",
        "superuser upsert",
        "migrate up",
        "superuser upsert",
    ]


def test_compose_grants_each_secret_only_to_its_intended_service() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]
    init = services["pocketbase-init"]
    pocketbase = services["pocketbase"]

    assert init["network_mode"] == "none"
    assert init["restart"] == "no"
    assert init["user"] == "0:0"
    assert init["entrypoint"] == ["/bin/sh", "/pb/init-superuser.sh"]
    assert init["command"] == []
    assert init["secrets"] == [
        "pocketbase_superuser_email",
        "pocketbase_superuser_password",
    ]
    assert init["volumes"] == pocketbase["volumes"]
    assert init["build"] == pocketbase["build"]
    assert init["image"] == pocketbase["image"] == "storylens-online-pocketbase:local"
    assert services["online-worker"]["secrets"] == [
        {
            "source": "storylens_online_aliyun_bailian_api_key",
            "target": "storylens_online_aliyun_bailian_api_key",
        }
    ]
    for service_name, service in services.items():
        if service_name not in {"pocketbase-init", "online-worker"}:
            assert "secrets" not in service

    assert pocketbase["depends_on"]["pocketbase-init"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["online-api"]["depends_on"]["pocketbase"]["condition"] == ("service_healthy")
    assert services["online-worker"]["depends_on"]["pocketbase"]["condition"] == ("service_healthy")


def test_only_gateway_publishes_ports_and_caddy_does_not_proxy_pocketbase() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    published = {
        service_name: service["ports"]
        for service_name, service in compose["services"].items()
        if "ports" in service
    }
    assert published == {"gateway": ["80:80", "443:443"]}
    assert "ports" not in compose["services"]["pocketbase"]
    assert "ports" not in compose["services"]["pocketbase-init"]

    caddy = CADDYFILE.read_text(encoding="utf-8").lower()
    assert "pocketbase" not in caddy
    assert "8090" not in caddy
    assert "/_/" not in caddy


def test_image_keeps_serve_nonroot_and_init_script_has_no_trace_mode() -> None:
    dockerfile = POCKETBASE_DOCKERFILE.read_text(encoding="utf-8")
    script = INIT_SCRIPT.read_text(encoding="utf-8")

    assert "su-exec" in dockerfile
    assert "USER pocketbase" in dockerfile
    assert "COPY --chown=root:root init-superuser.sh" in dockerfile
    assert "set -eu" in script
    assert "set -x" not in script
    assert ">/dev/null 2>&1" in script


def test_docker_compose_config_does_not_render_superuser_secret_values(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is unavailable")

    email_file = tmp_path / "compose-email.secret"
    password_file = tmp_path / "compose-password.secret"
    email_file.write_text(FAKE_EMAIL, encoding="utf-8")
    password_file.write_text(FAKE_PASSWORD, encoding="utf-8")
    env_file = tmp_path / "compose.env"
    env_file.write_text(
        "\n".join(
            [
                "STORYLENS_DOMAIN=online.example.invalid",
                "POSTGRES_PASSWORD=FAKE_DATABASE_PASSWORD_ONLY",
                "REDIS_PASSWORD=FAKE_REDIS_PASSWORD_ONLY",
                f"POCKETBASE_SUPERUSER_EMAIL_FILE={email_file.as_posix()}",
                f"POCKETBASE_SUPERUSER_PASSWORD_FILE={password_file.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            docker,
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(COMPOSE_FILE),
            "config",
        ],
        capture_output=True,
        check=False,
        cwd=INFRA_DIR,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, "Docker Compose config validation failed"
    rendered = result.stdout + result.stderr
    assert FAKE_EMAIL not in rendered
    assert FAKE_PASSWORD not in rendered
