"""Frozen asset_key / relation_key generation Contract (Phase 1B-P / Integration).

Does NOT implement entity disambiguation or whole-book analysis.
Agents E/F must call these helpers — never Python hash(), never DB auto-id alone.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


def _normalize_key_token(value: str) -> str:
    """Normalize identity tokens for keys and entity/alias names.

    Rules (Integration frozen):
    1. Unicode whitespace unified via NFKC category collapse
    2. Leading/trailing whitespace stripped
    3. Contiguous ordinary whitespace collapsed to a single space
    4. Case folded via ``casefold()`` (not ``lower()``)
    5. No simplified/traditional Chinese conversion
    6. No pinyin conversion
    7. Punctuation is kept (not stripped)
    8. No nickname guessing
    9. No role-name-specific rules
    10. CJK characters and digits remain distinctive
    """
    text = unicodedata.normalize("NFKC", value or "")
    # Unify all Unicode whitespace to ordinary space, then collapse.
    text = "".join(" " if ch.isspace() else ch for ch in text)
    collapsed = re.sub(r" +", " ", text.strip())
    return collapsed.casefold()


def build_asset_key(
    *,
    book_id: int,
    asset_type: str,
    stable_label: str,
    disambiguator: str = "",
) -> str:
    """Build a stable narrative asset_key.

    Rules (frozen):
    - Must not depend on database autoincrement id.
    - Must not use Python hash() (randomized per process).
    - Must not embed model-generated mutable summaries.
    - Uses SHA-256 over a canonical pipe-delimited payload.
    - ``stable_label`` should be a normalized title or structured fingerprint
      chosen by Agent E; ``disambiguator`` is an optional stable suffix when
      collisions are known (empty by default). Complex merge/disambiguation
      algorithms are out of scope for Phase 1B-P.
    """
    payload = "|".join(
        [
            "narrative_asset",
            str(int(book_id)),
            _normalize_key_token(asset_type),
            _normalize_key_token(stable_label),
            _normalize_key_token(disambiguator),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"na_{digest[:32]}"


def build_relation_key(
    *,
    book_id: int,
    source_asset_id: int,
    target_asset_id: int,
    identity_fingerprint: str,
    disambiguator: str = "",
) -> str:
    """Build a stable narrative relation_key (endpoints are stable Asset ids).

    ``identity_fingerprint`` expresses stable relation identity chosen by the
    caller. The underlying key tool must NOT couple the Version-level
    ``relation_type`` field to stable identity. Callers may include a
    normalized semantic type inside ``identity_fingerprint`` when that type
    is itself part of stable identity. Summary never participates.

    A→B differs from B→A. Books are isolated via ``book_id``.
    """
    fingerprint = _normalize_key_token(identity_fingerprint)
    if not fingerprint:
        raise ValueError("identity_fingerprint must not be empty after normalization")
    payload = "|".join(
        [
            "narrative_relation",
            str(int(book_id)),
            str(int(source_asset_id)),
            str(int(target_asset_id)),
            fingerprint,
            _normalize_key_token(disambiguator),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"nr_{digest[:32]}"


def normalize_entity_name(name: str) -> str:
    """Canonical normalized_name / normalized_alias helper (casefold)."""
    return _normalize_key_token(name)
