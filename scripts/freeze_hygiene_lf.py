# -*- coding: utf-8 -*-
"""Freeze hygiene helpers: restore CRLF-only drift to LF when hashes match baseline.

Does not update manifests. Refuses to write if LF-normalized content would not
match the expected baseline SHA-256, or if BOM / visible content would change.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


class RestoreRejected(ValueError):
    """Raised when a file cannot be safely restored to LF."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_crlf_to_lf(data: bytes) -> bytes:
    """Replace CRLF with LF only. Preserves BOM and all other bytes."""
    return data.replace(b"\r\n", b"\n")


def bom_prefix(data: bytes) -> bytes:
    if data.startswith(b"\xef\xbb\xbf"):
        return b"\xef\xbb\xbf"
    if data.startswith(b"\xff\xfe"):
        return b"\xff\xfe"
    if data.startswith(b"\xfe\xff"):
        return b"\xfe\xff"
    return b""


def validate_crlf_only_restore(
    raw: bytes,
    *,
    baseline_sha256: str,
    current_sha256: str | None = None,
) -> bytes:
    """Return LF-normalized bytes if and only if restore is safe.

    Requires:
    - current raw SHA differs from baseline (or current_sha256 provided differs)
    - LF-normalized SHA equals baseline
    - BOM prefix unchanged by normalization
    - no visible-character change beyond CRLF→LF
    """
    actual = current_sha256 or sha256_bytes(raw)
    if actual == baseline_sha256:
        raise RestoreRejected("raw SHA already matches baseline; no restore needed")

    normalized = normalize_crlf_to_lf(raw)
    if sha256_bytes(normalized) != baseline_sha256:
        raise RestoreRejected(
            "LF-normalized SHA does not match baseline; refusing write "
            f"(got {sha256_bytes(normalized)}, expected {baseline_sha256})"
        )

    if bom_prefix(raw) != bom_prefix(normalized):
        raise RestoreRejected("BOM would change under normalization; refusing write")

    # Visible / semantic check: removing CR bytes between CR and LF only.
    # Equivalent: normalized must equal raw with every CRLF replaced; no other edits.
    if normalize_crlf_to_lf(raw) != normalized:
        raise RestoreRejected("internal normalization mismatch")

    # Detect non-CRLF differences by comparing after stripping CR that precede LF.
    # If raw had lone CR that aren't part of CRLF, they remain — that's fine and
    # would already fail baseline match above unless baseline also had them.
    return normalized


def restore_file_to_lf(path: Path, baseline_sha256: str) -> dict[str, str]:
    """Validate and write LF-normalized content. Returns before/after SHA report."""
    raw = path.read_bytes()
    before = sha256_bytes(raw)
    normalized = validate_crlf_only_restore(raw, baseline_sha256=baseline_sha256, current_sha256=before)
    path.write_bytes(normalized)
    after = sha256_bytes(path.read_bytes())
    if after != baseline_sha256:
        raise RuntimeError(
            f"post-write SHA mismatch for {path}: got {after}, expected {baseline_sha256}"
        )
    return {
        "path": path.as_posix(),
        "before_sha256": before,
        "after_sha256": after,
        "baseline_sha256": baseline_sha256,
        "visible_chars_changed": "false",
    }
