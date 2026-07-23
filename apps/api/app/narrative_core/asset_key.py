"""Frozen asset_key / relation_key generation Contract (Phase 1B-P).

Does NOT implement entity disambiguation or whole-book analysis.
Agents E/F must call these helpers — never Python hash(), never DB auto-id alone.
"""

from __future__ import annotations

import hashlib
import re


def _normalize_key_token(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", (value or "").strip().lower())
    return collapsed


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
    relation_type: str,
    disambiguator: str = "",
) -> str:
    """Build a stable narrative relation_key (endpoints are stable Asset ids)."""
    payload = "|".join(
        [
            "narrative_relation",
            str(int(book_id)),
            str(int(source_asset_id)),
            str(int(target_asset_id)),
            _normalize_key_token(relation_type),
            _normalize_key_token(disambiguator),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"nr_{digest[:32]}"


def normalize_entity_name(name: str) -> str:
    """Canonical normalized_name / normalized_alias helper."""
    return _normalize_key_token(name)
