"""Offline, default-deny deployment policy. No application or secret imports."""

import re
from pathlib import PurePosixPath

FULL = "FULL_DEPLOYMENT_REQUIRED"
SUPPORT = ("VERSION",)
BUILD = {
    "web": ("infra/online/Dockerfile.web", "infra/online/nginx-online.conf"),
    "app": ("infra/online/Dockerfile.api", "infra/online/worker-entrypoint.sh"),
}
MODULE = {"web": "apps/online_web/", "app": "apps/online_api/"}
# Explicit audited ordinary logic; main.py mixes authentication/upload ownership
# and config/contracts/repository/providers mix security/billing, so stay FULL.
APP = {
    "apps/online_api/requirements.txt",
    "apps/online_api/storylens_online/worker.py",
    "apps/online_api/storylens_online/errors.py",
    "apps/online_api/storylens_online/services/queue.py",
    "apps/online_api/tests/test_worker_redis_reliability.py",
    "apps/online_api/tests/test_queue_contract.py",
}
FORBIDDEN_PARTS = {
    "node_modules",
    "dist",
    "__pycache__",
    ".git",
    ".venv",
    "uploads",
    "pb_data",
    "secrets",
    "dumps",
    "backups",
}


class DeployError(Exception):
    """Only fixed machine-readable error codes may escape the deployment CLI."""


def valid_path(path: str) -> bool:
    return (
        isinstance(path, str)
        and bool(re.fullmatch(r"[A-Za-z0-9_./@+-]+", path))
        and not path.startswith("/")
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def documentation(path: str) -> bool:
    return (
        path == "infra/online/README.md"
        or path.startswith("docs/online/")
        and path.endswith(".md")
        or bool(re.fullmatch(r"release/changes/CHG-\d{8}-\d{3}\.json", path))
    )


def classify(paths: list[str]) -> str:
    if any(not valid_path(path) for path in paths):
        return "invalid"
    levels = set()
    for path in paths:
        # Case changes cannot smuggle a Linux path past a Windows allowlist.
        if documentation(path):
            continue
        if path.startswith(MODULE["web"]) or path in BUILD["web"]:
            if not safe_payload_path(path, "web"):
                return "full"
            if re.search(
                r"(?:^|[/_.-])(auth|secret|security|billing|wallet|recharge|session|provider)(?:[/_.-]|$)",
                path,
                re.IGNORECASE,
            ):
                return "full"
            if path in {"apps/online_web/src/api.ts", "apps/online_web/src/api.test.ts"}:
                return "full"
            levels.add("web")
        elif path in APP:
            levels.add("app")
        else:
            return "full"
    return levels.pop() if len(levels) == 1 else "full" if levels else "documentation_only"


def require_mode(paths: list[str], mode: str) -> None:
    level = classify(paths)
    if level == "full":
        raise DeployError(FULL)
    if level == "invalid":
        raise DeployError("INVALID_PATH")
    if level == "documentation_only":
        raise DeployError("DOCUMENTATION_ONLY")
    if mode not in MODULE or level != mode:
        raise DeployError("MODE_MISMATCH")


def safe_payload_path(path: str, mode: str) -> bool:
    if not valid_path(path) or mode not in MODULE:
        return False
    if path in SUPPORT or path in BUILD[mode]:
        return True
    if not path.startswith(MODULE[mode]):
        return False
    parts = [part.lower() for part in path.split("/")]
    name = parts[-1]
    if set(parts) & FORBIDDEN_PARTS or name.startswith(".env") or name == "online.env":
        return False
    allowed = (
        {".py", ".txt"}
        if mode == "app"
        else {
            ".tsx",
            ".ts",
            ".js",
            ".jsx",
            ".json",
            ".css",
            ".html",
            ".svg",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".ico",
            ".woff",
            ".woff2",
            ".md",
        }
    )
    if mode == "app" and path.endswith(".txt"):
        return path == "apps/online_api/requirements.txt"
    return PurePosixPath(path).suffix.lower() in allowed


def scan_secret(data: bytes) -> None:
    # Conservative literal patterns, not a substitute for operator real-value audit.
    patterns = (
        rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----\r?\n",
        rb"\b(?:sk-|gh[pousr]_)[A-Za-z0-9_-]{32,}\b",
        rb"\bAKIA[A-Z0-9]{16}\b",
        rb"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
    )
    if any(re.search(pattern, data) for pattern in patterns):
        raise DeployError("SECRET_PATTERN_REJECTED")
