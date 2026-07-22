#!/usr/bin/env python3
"""Inspect a StoryLens Pro license code (verify signature; print payload fields)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.entitlement import app_major_version, load_license_config, public_keys_by_id  # noqa: E402
from app.services.license_crypto import LicenseError, parse_and_verify  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("license_code")
    parser.add_argument("--major-version", type=int, default=0)
    args = parser.parse_args()
    major = args.major_version or app_major_version()
    try:
        verified = parse_and_verify(
            args.license_code,
            public_keys_by_id=public_keys_by_id(load_license_config()),
            expected_major_version=major,
        )
    except LicenseError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "message": exc.message}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "payload": verified.payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
