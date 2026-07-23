"""Mock whole-book run metadata helpers (Phase 2A Agent M).

Persists Lab metadata in existing AnalysisRun.validated_output JSON.
No new DB columns / migrations. Schema/version required; silent field drop forbidden.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from app.narrative_core.run_shell_contract.create_run import (
    MOCK_RUN_METADATA_SCHEMA,
    MOCK_RUN_METADATA_VERSION,
    MockRunPersistenceMetadata,
)
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode, mock_run_error
from app.narrative_core.run_shell_contract.mock_lab import MOCK_ENGINE_ID, MOCK_LAB_SOURCE

# Documented: existing Text JSON columns are sufficient — no Schema Issue.
METADATA_STORAGE_COLUMN = "validated_output"
METADATA_SCHEMA_SUFFICIENT = True
METADATA_SCHEMA_ISSUES: tuple[str, ...] = ()


class MockRunMetadataError(Exception):
    def __init__(self, code: MockRunErrorCode, message: str | None = None) -> None:
        base = mock_run_error(code)
        self.code = code
        self.error = base
        self.message = message or base.message
        super().__init__(self.message)


REQUIRED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "version",
        "subject_type",
        "book_id",
        "book_snapshot_id",
        "run_scope",
        "analysis_mode",
        "requested_modules",
        "resolved_modules",
        "engine_id",
        "engine_version",
        "configuration_fingerprint",
        "mock",
        "non_production",
        "source",
    }
)


def build_mock_run_metadata(
    *,
    book_id: int,
    book_snapshot_id: int,
    analysis_mode: str,
    requested_modules: Sequence[str],
    resolved_modules: Sequence[str],
    engine_id: str,
    engine_version: str,
    configuration_fingerprint: str,
    preflight_fingerprint: str,
    mock_profile: str,
    requested_by: str,
    idempotency_key: str,
    idempotency_payload_hash: str,
    state_version: int = 0,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    core = MockRunPersistenceMetadata(
        schema=MOCK_RUN_METADATA_SCHEMA,
        version=MOCK_RUN_METADATA_VERSION,
        subject_type="book",
        book_id=int(book_id),
        book_snapshot_id=int(book_snapshot_id),
        run_scope="whole_book",
        analysis_mode=str(analysis_mode),
        requested_modules=tuple(str(m) for m in requested_modules),
        resolved_modules=tuple(str(m) for m in resolved_modules),
        engine_id=str(engine_id),
        engine_version=str(engine_version),
        configuration_fingerprint=str(configuration_fingerprint),
        mock=True,
        non_production=True,
        source=MOCK_LAB_SOURCE,
    )
    payload: dict[str, Any] = {
        "schema": core.schema,
        "version": core.version,
        "subject_type": core.subject_type,
        "book_id": core.book_id,
        "book_snapshot_id": core.book_snapshot_id,
        "run_scope": core.run_scope,
        "analysis_mode": core.analysis_mode,
        "requested_modules": list(core.requested_modules),
        "resolved_modules": list(core.resolved_modules),
        "engine_id": core.engine_id,
        "engine_version": core.engine_version,
        "configuration_fingerprint": core.configuration_fingerprint,
        "mock": True,
        "non_production": True,
        "source": core.source,
        "preflight_fingerprint": str(preflight_fingerprint),
        "mock_profile": str(mock_profile),
        "requested_by": str(requested_by),
        "idempotency_key": str(idempotency_key),
        "idempotency_payload_hash": str(idempotency_payload_hash),
        "state_version": int(state_version),
        "storage_column": METADATA_STORAGE_COLUMN,
    }
    if extra:
        for key, value in extra.items():
            if key in payload and payload[key] != value:
                raise MockRunMetadataError(
                    MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                    f"refusing to overwrite required metadata key: {key}",
                )
            payload.setdefault(key, value)
    return payload


def serialize_metadata(metadata: Mapping[str, Any]) -> str:
    validate_mock_run_metadata(metadata)
    return json.dumps(dict(metadata), ensure_ascii=False, sort_keys=True)


def parse_metadata_json(raw: str | None) -> dict[str, Any]:
    if raw is None or not str(raw).strip():
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET) from exc
    if not isinstance(data, dict):
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    return validate_mock_run_metadata(data)


def validate_mock_run_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(k for k in REQUIRED_METADATA_KEYS if k not in data)
    if missing:
        raise MockRunMetadataError(
            MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET,
            f"mock run metadata missing keys: {missing}",
        )
    if data.get("schema") != MOCK_RUN_METADATA_SCHEMA:
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    if data.get("version") != MOCK_RUN_METADATA_VERSION:
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    if data.get("source") != MOCK_LAB_SOURCE:
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    if data.get("engine_id") != MOCK_ENGINE_ID:
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    if data.get("run_scope") != "whole_book":
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    if data.get("subject_type") != "book":
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    if not data.get("mock") or not data.get("non_production"):
        raise MockRunMetadataError(MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET)
    # Reconstruct contract object to enforce frozen invariants.
    MockRunPersistenceMetadata(
        schema=str(data["schema"]),
        version=str(data["version"]),
        subject_type=str(data["subject_type"]),
        book_id=int(data["book_id"]),
        book_snapshot_id=int(data["book_snapshot_id"]),
        run_scope=str(data["run_scope"]),
        analysis_mode=str(data["analysis_mode"]),
        requested_modules=tuple(str(m) for m in data["requested_modules"]),
        resolved_modules=tuple(str(m) for m in data["resolved_modules"]),
        engine_id=str(data["engine_id"]),
        engine_version=str(data["engine_version"]),
        configuration_fingerprint=str(data["configuration_fingerprint"]),
        mock=bool(data["mock"]),
        non_production=bool(data["non_production"]),
        source=str(data["source"]),
    )
    return dict(data)


def is_mock_lab_run_metadata(raw: str | None) -> bool:
    try:
        parse_metadata_json(raw)
        return True
    except MockRunMetadataError:
        return False


def hash_create_payload(
    *,
    book_id: int,
    book_snapshot_id: int,
    analysis_mode: str,
    requested_modules: Sequence[str],
    configuration_fingerprint: str,
    preflight_fingerprint: str,
    mock_profile: str,
) -> str:
    canonical = {
        "book_id": int(book_id),
        "book_snapshot_id": int(book_snapshot_id),
        "analysis_mode": str(analysis_mode),
        "requested_modules": [str(m) for m in requested_modules],
        "configuration_fingerprint": str(configuration_fingerprint),
        "preflight_fingerprint": str(preflight_fingerprint),
        "mock_profile": str(mock_profile),
    }
    blob = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


__all__ = [
    "METADATA_SCHEMA_ISSUES",
    "METADATA_SCHEMA_SUFFICIENT",
    "METADATA_STORAGE_COLUMN",
    "REQUIRED_METADATA_KEYS",
    "MockRunMetadataError",
    "build_mock_run_metadata",
    "hash_create_payload",
    "is_mock_lab_run_metadata",
    "parse_metadata_json",
    "serialize_metadata",
    "validate_mock_run_metadata",
]
