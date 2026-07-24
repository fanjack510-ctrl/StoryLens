"""Private Lab run metadata helpers (Phase 2B-R1 Agent V).

Nested under AnalysisRun.validated_output[private_whole_book_lab_run_metadata].
No new columns / migrations. Merge preserves other validated_output keys.
Never stores novel body, Prompt, Credential, or Provider raw response.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_ENGINE_LAB_SOURCE,
    PRIVATE_LAB_ENGINE_ID,
    PRIVATE_LAB_ENGINE_VERSION,
    PRIVATE_LAB_RUN_METADATA_ENVELOPE_KEY,
    PRIVATE_LAB_RUN_METADATA_SCHEMA,
    PRIVATE_LAB_RUN_METADATA_VERSION,
)

METADATA_STORAGE_COLUMN = "validated_output"
METADATA_ENVELOPE_KEY = PRIVATE_LAB_RUN_METADATA_ENVELOPE_KEY

REQUIRED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "version",
        "private_lab",
        "non_production",
        "book_id",
        "snapshot_id",
        "analysis_mode",
        "requested_modules",
        "resolved_modules",
        "provider_key",
        "model_id",
        "quality_profile",
        "engine_id",
        "engine_version",
        "prompt_pack_id",
        "prompt_pack_version",
        "context_bundle_hash",
        "estimate_fingerprint",
        "consent_fingerprint",
        "configuration_fingerprint",
        "data_transfer_manifest_hash",
        "output_locale",
        "source_language",
        "create_idempotency_key",
        "created_at",
    }
)

_FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "full_text",
        "novel_body",
        "prompt",
        "prompt_body",
        "system_prompt",
        "api_key",
        "credential",
        "credentials",
        "raw_response",
        "provider_raw_response",
    }
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hash_create_payload(payload: Mapping[str, Any]) -> str:
    cleaned = {k: v for k, v in payload.items() if k not in _FORBIDDEN_METADATA_KEYS}
    blob = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_private_lab_run_metadata(
    *,
    book_id: int,
    snapshot_id: int,
    analysis_mode: str,
    requested_modules: Sequence[str],
    resolved_modules: Sequence[str],
    provider_key: str,
    model_id: str,
    quality_profile: str,
    engine_id: str = PRIVATE_LAB_ENGINE_ID,
    engine_version: str = PRIVATE_LAB_ENGINE_VERSION,
    prompt_pack_id: str,
    prompt_pack_version: str,
    context_bundle_hash: str,
    estimate_fingerprint: str,
    consent_fingerprint: str,
    configuration_fingerprint: str,
    data_transfer_manifest_hash: str,
    output_locale: str = "zh-CN",
    source_language: str = "zh",
    create_idempotency_key: str,
    created_at: str | None = None,
    state_version: int = 0,
    dry_run: bool = True,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": PRIVATE_LAB_RUN_METADATA_SCHEMA,
        "version": PRIVATE_LAB_RUN_METADATA_VERSION,
        "private_lab": True,
        "non_production": True,
        "mock": False,
        "book_id": int(book_id),
        "snapshot_id": int(snapshot_id),
        "book_snapshot_id": int(snapshot_id),
        "analysis_mode": str(analysis_mode),
        "requested_modules": [str(m) for m in requested_modules],
        "resolved_modules": [str(m) for m in resolved_modules],
        "provider_key": str(provider_key),
        "model_id": str(model_id),
        "quality_profile": str(quality_profile),
        "engine_id": str(engine_id),
        "engine_version": str(engine_version),
        "prompt_pack_id": str(prompt_pack_id),
        "prompt_pack_version": str(prompt_pack_version),
        "context_bundle_hash": str(context_bundle_hash),
        "estimate_fingerprint": str(estimate_fingerprint),
        "consent_fingerprint": str(consent_fingerprint),
        "configuration_fingerprint": str(configuration_fingerprint),
        "data_transfer_manifest_hash": str(data_transfer_manifest_hash),
        "output_locale": str(output_locale),
        "source_language": str(source_language),
        "create_idempotency_key": str(create_idempotency_key),
        "idempotency_key": str(create_idempotency_key),
        "created_at": created_at or _utc_now_iso(),
        "state_version": int(state_version),
        "dry_run": bool(dry_run),
        "source": PRIVATE_ENGINE_LAB_SOURCE,
        "storage_column": METADATA_STORAGE_COLUMN,
    }
    if extra:
        for key, value in extra.items():
            if key in _FORBIDDEN_METADATA_KEYS:
                raise ValueError(f"forbidden metadata key: {key}")
            if key in REQUIRED_METADATA_KEYS and key in payload and payload[key] != value:
                raise ValueError(f"refusing to overwrite required metadata key: {key}")
            payload[key] = value
    missing = REQUIRED_METADATA_KEYS - payload.keys()
    if missing:
        raise ValueError(f"missing required private lab metadata keys: {sorted(missing)}")
    return payload


def serialize_metadata(
    metadata: Mapping[str, Any],
    *,
    existing_validated_output: str | None = None,
) -> str:
    root: dict[str, Any] = {}
    if existing_validated_output and str(existing_validated_output).strip():
        try:
            parsed = json.loads(existing_validated_output)
            if isinstance(parsed, dict):
                root = dict(parsed)
        except json.JSONDecodeError:
            root = {}
    # Nested merge — do not clobber sibling keys.
    root[METADATA_ENVELOPE_KEY] = dict(metadata)
    return json.dumps(root, ensure_ascii=False, sort_keys=True)


def parse_metadata_json(validated_output: str | None) -> dict[str, Any]:
    if not validated_output or not str(validated_output).strip():
        return {}
    try:
        parsed = json.loads(validated_output)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    node = parsed.get(METADATA_ENVELOPE_KEY)
    if isinstance(node, dict):
        return dict(node)
    return {}


def is_private_lab_run_metadata(validated_output: str | None) -> bool:
    meta = parse_metadata_json(validated_output)
    if not meta:
        return False
    return (
        meta.get("schema") == PRIVATE_LAB_RUN_METADATA_SCHEMA
        and meta.get("private_lab") is True
        and meta.get("non_production") is True
        and meta.get("mock") is not True
    )


def assert_not_forgeable_on_non_private(metadata: Mapping[str, Any]) -> None:
    """Non-Private runs must not carry private_lab=true forge metadata."""

    if metadata.get("private_lab") is True and metadata.get("schema") != PRIVATE_LAB_RUN_METADATA_SCHEMA:
        raise ValueError("private_lab flag requires private lab metadata schema")


__all__ = [
    "METADATA_ENVELOPE_KEY",
    "METADATA_STORAGE_COLUMN",
    "REQUIRED_METADATA_KEYS",
    "assert_not_forgeable_on_non_private",
    "build_private_lab_run_metadata",
    "hash_create_payload",
    "is_private_lab_run_metadata",
    "parse_metadata_json",
    "serialize_metadata",
]
