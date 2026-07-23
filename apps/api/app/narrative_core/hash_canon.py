"""Canonical text hashing for narrative content (Phase 1P).

Rules (frozen):
- Normalize CRLF and CR to LF only.
- Do not strip semantically meaningful whitespace.
- Do not apply Unicode NFC/NFKC (CJK presentation must remain byte-stable
  relative to stored DB text after newline normalization only).
- Do not use Python's built-in hash().
- Digest algorithm: SHA-256, lowercase hex.
"""

from __future__ import annotations

import hashlib


def canonicalize_text(text: str) -> str:
    """Return platform-stable text for hashing."""
    if text is None:
        raise TypeError("text must be str, not None")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def calculate_text_hash(text: str) -> str:
    """SHA-256 hex digest of canonicalize_text(text) encoded as UTF-8."""
    canonical = canonicalize_text(text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
