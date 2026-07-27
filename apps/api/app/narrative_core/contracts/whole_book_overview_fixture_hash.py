"""Mirror of packages/contracts/.../fixture_hash.py for Public imports.

Private should copy or symlink the packages fixture tree and use the same
hash rules / FIXTURE_MANIFEST.json (contract_version + per-file sha256).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "1.0"
FIXTURE_SET = "whole_book_overview_v1"
CANONICAL_FIXTURE_DIR = Path("packages") / "contracts" / "fixtures" / "whole_book_overview_v1"


def sha256_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))


def fixture_dir_from_repo_root(repo_root: Path) -> Path:
    return repo_root / CANONICAL_FIXTURE_DIR


def load_manifest(fixture_dir: Path) -> dict[str, Any]:
    return json.loads((fixture_dir / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))


def compute_file_hashes(fixture_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(fixture_dir.glob("*.json")):
        if path.name == "FIXTURE_MANIFEST.json":
            continue
        hashes[path.name] = sha256_file(path)
    return hashes


def combined_sha256(file_hashes: dict[str, str]) -> str:
    combined_src = "".join(f"{key}:{value}\n" for key, value in sorted(file_hashes.items()))
    return hashlib.sha256(combined_src.encode("utf-8")).hexdigest()


def verify_fixture_manifest(fixture_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(fixture_dir)
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(
            f"manifest contract_version={manifest.get('contract_version')} "
            f"expected={CONTRACT_VERSION}"
        )
    expected_files: dict[str, str] = dict(manifest.get("files") or {})
    actual = compute_file_hashes(fixture_dir)
    if set(actual) != set(expected_files):
        raise ValueError(
            f"fixture file set mismatch: actual={sorted(actual)} "
            f"expected={sorted(expected_files)}"
        )
    for name, digest in expected_files.items():
        if actual[name] != digest:
            raise ValueError(f"fixture hash mismatch for {name}")
    expected_combined = manifest.get("combined_sha256")
    actual_combined = combined_sha256(actual)
    if expected_combined != actual_combined:
        raise ValueError(
            f"combined_sha256 mismatch: actual={actual_combined} "
            f"expected={expected_combined}"
        )
    return manifest


def default_public_fixture_dir() -> Path:
    """Resolve canonical Public fixture directory from this module location."""
    # apps/api/app/narrative_core/contracts/ → repo root is parents[5]
    return Path(__file__).resolve().parents[5] / CANONICAL_FIXTURE_DIR
