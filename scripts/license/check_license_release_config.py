#!/usr/bin/env python3
"""Pre-release checks for StoryLens Pro offline license configuration.

Does not publish, build, or call Afdian. Safe to run locally before a real release.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD_CONFIG = ROOT / "config" / "license_public_keys.production.json"
TEST_FIXTURE = ROOT / "tests" / "fixtures" / "license_public_keys.test.json"
VERSION_FILE = ROOT / "VERSION"
LEGACY_COMBINED = ROOT / "config" / "license_public_keys.json"

PRIV_PATTERNS = (
    re.compile(r"-----BEGIN (?:ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(r"[A-Za-z0-9_-]{40,}\.ed25519\.priv\.b64"),
)
CODE_LINE_RE = re.compile(r"^SLP1-[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
SKIP_SECRET_SCAN_PREFIXES = (
    "docs/",
    "scripts/license/",
    "scripts/check_release_artifacts.ps1",
    "apps/api/tests/",
    "apps/desktop/src/",
)


def _fail(msg: str, errors: list[str]) -> None:
    errors.append(msg)
    print(f"FAIL: {msg}")


def _ok(msg: str) -> None:
    print(f"OK: {msg}")


def _b64url_ok(raw: str) -> bool:
    try:
        pad = "=" * (-len(raw) % 4)
        data = base64.urlsafe_b64decode(raw + pad)
        return len(data) == 32
    except Exception:  # noqa: BLE001
        return False


def check_production_config(errors: list[str], *, allow_missing_commerce: bool = False) -> dict:
    if not PROD_CONFIG.is_file():
        _fail(f"missing {PROD_CONFIG.relative_to(ROOT)}", errors)
        return {}
    _ok("production public key config exists")
    data = json.loads(PROD_CONFIG.read_text(encoding="utf-8"))
    keys = [k for k in (data.get("keys") or []) if isinstance(k, dict)]
    prod_keys = [k for k in keys if str(k.get("environment") or "").lower() == "production"]
    if not prod_keys:
        _fail("production config has no production key entries", errors)
    else:
        _ok(f"found {len(prod_keys)} production key entr(y/ies)")

    for key in keys:
        key_id = str(key.get("key_id") or "")
        env = str(key.get("environment") or "").lower()
        if env == "test" or key_id == "test-dev-001" or key_id.startswith("test-"):
            _fail(f"production config must not include test key {key_id!r}", errors)
        pub = str(key.get("public_key_b64url") or "").strip()
        status = str(key.get("status") or "")
        if pub and not _b64url_ok(pub):
            _fail(f"invalid public key format for {key_id}", errors)
        if status in {"active", "readonly"} and pub and _b64url_ok(pub):
            _ok(f"usable production key format: {key_id}")
        elif status == "pending_issuance":
            _ok(f"pending production key placeholder present: {key_id}")

    commerce = data.get("commerce") or {}
    url = str(commerce.get("afdian_product_url") or "").strip()
    if not url.startswith("https://"):
        if allow_missing_commerce:
            _ok("afdian product URL empty (allowed by --allow-missing-commerce)")
        else:
            _fail("commerce.afdian_product_url must be a configured https URL before release", errors)
    else:
        _ok("afdian product URL configured")

    if LEGACY_COMBINED.is_file():
        _fail("legacy combined config/license_public_keys.json must be removed", errors)
    else:
        _ok("no legacy combined license_public_keys.json")
    return data


def check_repo_secrets(errors: list[str]) -> None:
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files"],
        text=True,
        encoding="utf-8",
    ).splitlines()
    for rel in tracked:
        norm = rel.replace("\\", "/")
        if any(norm.startswith(prefix) or norm == prefix for prefix in SKIP_SECRET_SCAN_PREFIXES):
            continue
        if norm.endswith("check_license_release_config.py"):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in PRIV_PATTERNS:
            if pat.search(text):
                _fail(f"tracked file may contain private-key material: {rel}", errors)
                break
        if any(CODE_LINE_RE.match(line.strip()) for line in text.splitlines()):
            _fail(f"tracked file appears to contain a real SLP1 license code: {rel}", errors)
    for bad in ROOT.rglob("*.ed25519.priv.b64"):
        rel = bad.relative_to(ROOT)
        listed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", str(rel)],
            capture_output=True,
            text=True,
        )
        if listed.returncode == 0:
            _fail(f"private key is tracked by git: {rel}", errors)
    _ok("no private key files tracked by git (scan complete)")

def check_version(errors: list[str]) -> None:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if version != "1.0.3":
        _fail(f"VERSION expected 1.0.3, got {version}", errors)
    else:
        _ok("VERSION is 1.0.3")


def check_test_fixture_isolated(errors: list[str]) -> None:
    if not TEST_FIXTURE.is_file():
        _fail("missing test fixture license_public_keys.test.json", errors)
        return
    data = json.loads(TEST_FIXTURE.read_text(encoding="utf-8"))
    for key in data.get("keys") or []:
        if str(key.get("environment") or "").lower() == "production":
            _fail("test fixture must not contain production keys", errors)
            return
    _ok("test fixture present and free of production keys")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-pending-keys",
        action="store_true",
        help="Do not fail when production public keys are still pending_issuance / empty.",
    )
    parser.add_argument(
        "--allow-missing-commerce",
        action="store_true",
        help="Do not fail when afdian_product_url is still empty (script dry-run).",
    )
    args = parser.parse_args()
    errors: list[str] = []
    prod = check_production_config(errors, allow_missing_commerce=args.allow_missing_commerce)
    if not args.allow_pending_keys and prod:
        usable = False
        for key in prod.get("keys") or []:
            if (
                str(key.get("environment") or "").lower() == "production"
                and key.get("status") in {"active", "readonly"}
                and str(key.get("public_key_b64url") or "").strip()
                and _b64url_ok(str(key.get("public_key_b64url") or "").strip())
            ):
                usable = True
        if not usable:
            _fail("no active production public key with valid material", errors)
    check_test_fixture_isolated(errors)
    check_repo_secrets(errors)
    check_version(errors)
    if errors:
        print(f"\n{len(errors)} check(s) failed.")
        return 1
    print("\nAll license release config checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
