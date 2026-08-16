"""Issue a signed StoryLens Pro license code — the 爱发电 fulfilment tool.

Runs OFF the user's machine, wherever the private key lives. Typical monthly-card flow:
a buyer completes an 爱发电 order, the operator runs this with --valid-days 31 and sends
the printed code back; the buyer pastes it into 设置 → 授权激活.

    python scripts/issue_license.py --private-key <b64url> --key-id prod-2026-01 --valid-days 31
    python scripts/issue_license.py --private-key <b64url> --key-id prod-2026-01            # perpetual

The private key is never read from the repo; pass it explicitly or via
STORYLENS_LICENSE_PRIVATE_KEY. --valid-days 0 (default) issues a perpetual license.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.services.license_crypto import (  # noqa: E402
    build_unsigned_payload,
    encode_license,
    load_private_key_b64url,
    peek_license_payload,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--private-key", default=os.environ.get("STORYLENS_LICENSE_PRIVATE_KEY", ""),
                    help="Ed25519 private key, b64url (or env STORYLENS_LICENSE_PRIVATE_KEY)")
    ap.add_argument("--key-id", required=True, help="key_id matching an entry in the public-key config")
    ap.add_argument("--major", type=int, default=1, help="app major version the license binds to")
    ap.add_argument("--valid-days", type=int, default=0,
                    help="0 = perpetual; 31 = 爱发电月卡")
    args = ap.parse_args()

    if not args.private_key:
        print("missing --private-key / STORYLENS_LICENSE_PRIVATE_KEY", file=sys.stderr)
        return 2

    valid_until = None
    if args.valid_days > 0:
        valid_until = (
            (datetime.now(timezone.utc) + timedelta(days=args.valid_days))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    payload = build_unsigned_payload(
        major_version=args.major, key_id=args.key_id, valid_until=valid_until,
    )
    code = encode_license(payload, load_private_key_b64url(args.private_key))
    # Round-trip sanity before anything is sent to a buyer.
    peeked = peek_license_payload(code)
    assert peeked["license_id"] == payload["license_id"]

    print(code)
    print(f"# license_id={payload['license_id']}", file=sys.stderr)
    print(f"# valid_until={valid_until or 'perpetual'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
