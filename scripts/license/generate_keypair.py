#!/usr/bin/env python3
"""Generate Ed25519 keypairs for StoryLens Pro offline licenses.

Private keys are written under private_release/ (gitignored).
Public keys are merged into config/license_public_keys.json.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("test", "production"), default="test")
    parser.add_argument("--key-id", default="")
    args = parser.parse_args()

    key_id = args.key_id or (
        f"test-dev-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        if args.env == "test"
        else f"prod-{datetime.now(timezone.utc).strftime('%Y%m')}"
    )
    priv = Ed25519PrivateKey.generate()
    priv_b64 = private_key_b64url(priv)
    pub_b64 = public_key_b64url(priv.public_key())

    out_dir = ROOT / "private_release" / "license_keys"
    out_dir.mkdir(parents=True, exist_ok=True)
    priv_path = out_dir / f"{key_id}.ed25519.priv.b64"
    priv_path.write_text(priv_b64 + "\n", encoding="utf-8")

    config_path = ROOT / "config" / "license_public_keys.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    keys = [k for k in config.get("keys", []) if k.get("key_id") != key_id]
    keys.append(
        {
            "key_id": key_id,
            "signature_version": 1,
            "algorithm": "ed25519",
            "environment": args.env,
            "public_key_b64url": pub_b64,
            "status": "active",
        }
    )
    config["keys"] = keys
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Private key (KEEP SECRET): {priv_path}")
    print(f"Public key updated: {config_path}")
    print(f"key_id={key_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
