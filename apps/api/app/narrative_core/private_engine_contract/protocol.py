"""Private Engine execution Protocol DTOs (Phase 2B-P).

Protocol id: storylens.private_engine.v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
)
from app.narrative_core.private_engine_contract.manifest import PRIVATE_ENGINE_PROTOCOL_ID

# Re-export for Protocol surface consumers.
__all__ = [
    "PRIVATE_ENGINE_PROTOCOL_ID",
    "PrivateEngineCheckpoint",
    "PrivateEngineError",
    "PrivateEngineErrorCode",
    "PrivateEngineExecutionRequest",
    "PrivateEngineExecutionResult",
    "PrivateEngineHealth",
    "assert_request_has_no_forbidden_fields",
    "assert_mapping_has_no_forbidden_keys",
]

FORBIDDEN_REQUEST_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "api_key",
        "apiKey",
        "credential",
        "credentials",
        "full_text",
        "fullText",
        "novel_body",
        "novelBody",
        "license",
        "license_payload",
        "payment",
        "payment_info",
        "allowed",  # frontend-provided capability allowed must not ride request
    }
)


def assert_mapping_has_no_forbidden_keys(payload: Mapping[str, Any], *, label: str = "payload") -> None:
    lower_map = {str(k).lower(): k for k in payload}
    for forbidden in FORBIDDEN_REQUEST_FIELD_NAMES:
        if forbidden.lower() in lower_map:
            raise ValueError(f"{label} must not include forbidden field: {forbidden}")


def assert_request_has_no_forbidden_fields(request: PrivateEngineExecutionRequest) -> None:
    # Dataclass fields are fixed; also guard optional policy mappings.
    for policy in (request.provider_policy, request.budget_policy):
        if policy:
            assert_mapping_has_no_forbidden_keys(policy, label="policy")


@dataclass(frozen=True, slots=True)
class PrivateEngineCheckpoint:
    protocol_version: str
    engine_id: str
    engine_version: str
    module_key: str | None
    module_version: str | None
    stage_key: str | None
    attempt: int
    prompt_pack_id: str | None
    prompt_pack_version: str | None
    provider_policy_key: str | None
    quality_profile: str | None
    context_bundle_hash: str | None
    configuration_fingerprint: str
    book_snapshot_id: int
    completed_units: tuple[str, ...] = ()
    pending_units: tuple[str, ...] = ()
    output_fingerprints: tuple[str, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    integrity_hash: str = ""

    def __post_init__(self) -> None:
        if self.attempt < 0:
            raise ValueError("attempt must be >= 0")
        if self.protocol_version != PRIVATE_ENGINE_PROTOCOL_ID:
            raise ValueError("checkpoint protocol_version must be storylens.private_engine.v1")


@dataclass(frozen=True, slots=True)
class PrivateEngineHealth:
    engine_id: str
    healthy: bool
    status: str
    protocol_version: str = PRIVATE_ENGINE_PROTOCOL_ID
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PrivateEngineExecutionRequest:
    run_id: int
    stage_key: WholeBookStageKey | str
    attempt: int
    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    requested_module_keys: tuple[WholeBookModuleKey, ...]
    resolved_module_keys: tuple[WholeBookModuleKey, ...]
    context_bundle_ref: str
    provider_policy: Mapping[str, Any]
    budget_policy: Mapping[str, Any]
    output_locale: str
    source_language: str
    configuration_fingerprint: str
    prompt_pack_ref: str
    cancellation_ref: str | None
    checkpoint_ref: str | None
    mock: bool
    requested_at: datetime
    run_stage_id: int | None = None

    def __post_init__(self) -> None:
        if self.run_id <= 0:
            raise ValueError("run_id must be positive")
        if self.attempt < 0:
            raise ValueError("attempt must be >= 0")
        if not self.configuration_fingerprint.strip():
            raise ValueError("configuration_fingerprint is required")
        if not self.context_bundle_ref.strip():
            raise ValueError("context_bundle_ref is required")
        assert_request_has_no_forbidden_fields(self)


@dataclass(frozen=True, slots=True)
class PrivateEngineExecutionResult:
    schema: str
    version: str
    engine_id: str
    engine_version: str
    stage_key: str
    attempt: int
    status: str
    module_outputs: Mapping[str, Any]
    evidence_candidates: tuple[Any, ...]
    asset_candidates: tuple[Any, ...]
    relation_candidates: tuple[Any, ...]
    conflict_candidates: tuple[Any, ...]
    checkpoint: PrivateEngineCheckpoint | None
    usage: Mapping[str, Any]
    warnings: tuple[str, ...]
    validation_summary: Mapping[str, Any]
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.attempt < 0:
            raise ValueError("attempt must be >= 0")
        assert_mapping_has_no_forbidden_keys(self.usage, label="usage")
        assert_mapping_has_no_forbidden_keys(self.validation_summary, label="validation_summary")
