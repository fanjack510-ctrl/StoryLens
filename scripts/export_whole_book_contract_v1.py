#!/usr/bin/env python3
"""Export whole_book_contract_v1 Public/Private schemas + identity evidence.

Outputs under release/evidence/whole-book/WB-0.2/:
  PUBLIC_CONTRACT_SCHEMA.json
  PRIVATE_CONTRACT_SCHEMA.json
  CONTRACT_MANIFEST.json
  SCHEMA_IDENTITY.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _git_head(repo: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return "unknown"


def _load_public(public_root: Path):
    api = public_root / "apps" / "api"
    sys.path.insert(0, str(api))
    from app.narrative_core.contracts.whole_book_contract_v1 import (  # noqa: WPS433
        ENUM_NAMES_V1,
        WIRE_MODEL_NAMES_V1,
        WHOLE_BOOK_CONTRACT_VERSION,
        WHOLE_BOOK_SCHEMA_NAME,
        build_public_only_schema,
        build_wire_contract_schema,
        canonical_json_bytes,
        schema_sha256,
    )

    return {
        "WHOLE_BOOK_CONTRACT_VERSION": WHOLE_BOOK_CONTRACT_VERSION,
        "WHOLE_BOOK_SCHEMA_NAME": WHOLE_BOOK_SCHEMA_NAME,
        "WIRE_MODEL_NAMES_V1": WIRE_MODEL_NAMES_V1,
        "ENUM_NAMES_V1": ENUM_NAMES_V1,
        "build_wire_contract_schema": build_wire_contract_schema,
        "build_public_only_schema": build_public_only_schema,
        "canonical_json_bytes": canonical_json_bytes,
        "schema_sha256": schema_sha256,
    }


def _load_private(private_root: Path):
    src = private_root / "src"
    sys.path.insert(0, str(src))
    from storylens_private_engine.contracts.whole_book_contract_v1 import (  # noqa: WPS433
        build_wire_contract_schema,
        schema_sha256,
    )

    return {
        "build_wire_contract_schema": build_wire_contract_schema,
        "schema_sha256": schema_sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--public-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--private-root",
        type=Path,
        default=Path(r"D:\Dstorylens-private-engine-wt-whole-book-v120-integration"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    public_root: Path = args.public_root
    private_root: Path = args.private_root
    out_dir = args.out_dir or (public_root / "release" / "evidence" / "whole-book" / "WB-0.2")
    out_dir.mkdir(parents=True, exist_ok=True)

    pub = _load_public(public_root)
    priv = _load_private(private_root)

    public_schema = pub["build_wire_contract_schema"]()
    private_schema = priv["build_wire_contract_schema"]()
    public_only = pub["build_public_only_schema"]()

    public_sha = pub["schema_sha256"](public_schema)
    private_sha = priv["schema_sha256"](private_schema)
    identity = "PASS" if public_sha == private_sha else "FAIL"

    (out_dir / "PUBLIC_CONTRACT_SCHEMA.json").write_text(
        json.dumps(public_schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "PRIVATE_CONTRACT_SCHEMA.json").write_text(
        json.dumps(private_schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "PUBLIC_ONLY_PERSISTENCE_SCHEMA.json").write_text(
        json.dumps(public_only, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "contract_version": pub["WHOLE_BOOK_CONTRACT_VERSION"],
        "schema_name": pub["WHOLE_BOOK_SCHEMA_NAME"],
        "public_head": _git_head(public_root),
        "private_head": _git_head(private_root),
        "public_schema_sha256": public_sha,
        "private_schema_sha256": private_sha,
        "model_count": len(pub["WIRE_MODEL_NAMES_V1"]),
        "enum_count": len(pub["ENUM_NAMES_V1"]),
        "wire_model_names": list(pub["WIRE_MODEL_NAMES_V1"]),
        "enum_names": list(pub["ENUM_NAMES_V1"]),
        "generated_at": generated_at,
        "identity": identity,
    }
    (out_dir / "CONTRACT_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    identity_doc = {
        "public_schema_sha256": public_sha,
        "private_schema_sha256": private_sha,
        "identity": identity,
    }
    (out_dir / "SCHEMA_IDENTITY.json").write_text(
        json.dumps(identity_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"PUBLIC_SCHEMA_SHA={public_sha}")
    print(f"PRIVATE_SCHEMA_SHA={private_sha}")
    print(f"IDENTITY={identity}")
    return 0 if identity == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
