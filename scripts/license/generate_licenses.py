#!/usr/bin/env python3
"""Batch-generate StoryLens Pro offline license codes for Afdian fulfillment."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.license_crypto import (  # noqa: E402
    build_unsigned_payload,
    encode_license,
    load_private_key_b64url,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", default="storylens_pro")
    parser.add_argument("--major-version", type=int, default=1)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--key-id", required=True)
    parser.add_argument(
        "--private-key-file",
        type=Path,
        required=True,
        help="Path to issuer private key (.ed25519.priv.b64 under private_release/).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("private_release/afdian_storylens_pro_1x_codes.txt"),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("private_release/afdian_storylens_pro_1x_ledger.csv"),
    )
    args = parser.parse_args()
    if args.product != "storylens_pro":
        raise SystemExit("Only storylens_pro is supported in V1.")

    private = load_private_key_b64url(args.private_key_file.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)

    codes: list[str] = []
    rows: list[dict[str, str]] = []
    issued = datetime.now(timezone.utc).isoformat()
    for _ in range(args.count):
        payload = build_unsigned_payload(
            major_version=args.major_version,
            key_id=args.key_id,
        )
        code = encode_license(payload, private)
        codes.append(code)
        rows.append(
            {
                "license_id": payload["license_id"],
                "product_code": payload["product_code"],
                "major_version": str(payload["major_version"]),
                "key_id": args.key_id,
                "generated_at": issued,
                "license_code": code,
            }
        )

    args.output.write_text("\n".join(codes) + "\n", encoding="utf-8")
    with args.ledger.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "license_id",
                "product_code",
                "major_version",
                "key_id",
                "generated_at",
                "license_code",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(codes)} codes -> {args.output}")
    print(f"Issuer ledger -> {args.ledger}")
    print("Do not upload the ledger CSV to Afdian; upload only the one-code-per-line file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
