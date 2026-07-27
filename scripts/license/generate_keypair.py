#!/usr/bin/env python3
"""Generate Ed25519 keypairs for StoryLens Pro offline licenses.

Production private keys MUST be written outside the git worktree
(recommended: D:\\StoryLens-License-Secrets\\production\\).
This script never auto-copies private keys into the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app.services.license_crypto import private_key_b64url, public_key_b64url  # noqa: E402


def _ensure_outside_repo(path: Path, *, label: str) -> None:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    raise SystemExit(
        f"{label} must be outside the repository (got {resolved}). "
        "Recommended: D:\\StoryLens-License-Secrets\\production\\"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("test", "production"), default="test")
    parser.add_argument("--key-id", default="")
    parser.add_argument(
        "--private-key-output",
        type=Path,
        help="Where to write the private key (.ed25519.priv.b64). Required for production.",
    )
    parser.add_argument(
        "--public-key-output",
        type=Path,
        help="Where to write the public key (.ed25519.pub.b64).",
    )
    parser.add_argument(
        "--update-test-fixture",
        action="store_true",
        help="Only for --env test: merge public key into tests/fixtures/license_public_keys.test.json",
    )
    args = parser.parse_args()

    key_id = args.key_id or (
        f"test-dev-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        if args.env == "test"
        else f"storylens-pro-1-prod-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    )

    if args.env == "production":
        if not args.private_key_output or not args.public_key_output:
            raise SystemExit(
                "Production requires --private-key-output and --public-key-output "
                "outside the repository. Public keys are pasted into "
                "config/license_public_keys.production.json manually."
            )
        _ensure_outside_repo(args.private_key_output, label="Production private key")
        _ensure_outside_repo(args.public_key_output, label="Production public key export")
        if args.update_test_fixture:
            raise SystemExit("Refusing --update-test-fixture for production keys.")

    priv = Ed25519PrivateKey.generate()
    priv_b64 = private_key_b64url(priv)
    pub_b64 = public_key_b64url(priv.public_key())

    if args.private_key_output:
        priv_path = args.private_key_output.expanduser()
        priv_path.parent.mkdir(parents=True, exist_ok=True)
        priv_path.write_text(priv_b64 + "\n", encoding="utf-8")
    elif args.env == "test":
        # Temporary local-only path for regenerating the shared test fixture.
        priv_path = ROOT / "private_release" / "license_keys" / f"{key_id}.ed25519.priv.b64"
        priv_path.parent.mkdir(parents=True, exist_ok=True)
        priv_path.write_text(priv_b64 + "\n", encoding="utf-8")
    else:
        raise SystemExit("Missing --private-key-output")

    if args.public_key_output:
        pub_path = args.public_key_output.expanduser()
        pub_path.parent.mkdir(parents=True, exist_ok=True)
        pub_path.write_text(pub_b64 + "\n", encoding="utf-8")
    else:
        pub_path = None

    if args.env == "test" and args.update_test_fixture:
        fixture = ROOT / "tests" / "fixtures" / "license_public_keys.test.json"
        config = json.loads(fixture.read_text(encoding="utf-8"))
        keys = [k for k in config.get("keys", []) if k.get("key_id") != key_id]
        keys.append(
            {
                "key_id": key_id,
                "signature_version": 1,
                "algorithm": "ed25519",
                "environment": "test",
                "public_key_b64url": pub_b64,
                "status": "active",
            }
        )
        config["keys"] = keys
        fixture.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Test fixture updated: {fixture}")

    print(f"key_id={key_id}")
    print(f"Private key path: {priv_path}")
    if pub_path:
        print(f"Public key path: {pub_path}")
    if args.env == "production":
        print(
            "Next: manually paste public_key_b64url into "
            "config/license_public_keys.production.json (do not commit the private key)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
