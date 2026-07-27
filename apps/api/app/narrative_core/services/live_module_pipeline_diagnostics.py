"""Safe Live module pipeline diagnostics (CHG-055).

Counters and codes only — never bodies, prompts, credentials, or raw responses.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class LiveModulePipelineDiagnostics:
    module_key: str = ""
    run_id: int | None = None
    stage_id: int | None = None
    structured_output_present: bool = False
    structured_output_schema: str | None = None
    structured_output_fingerprint: str | None = None
    structured_output_runtime_type: str | None = None
    structured_output_top_level_fields: list[str] = field(default_factory=list)
    structured_output_nonempty_fields: list[str] = field(default_factory=list)
    claim_count: int = 0
    semantic_source_field_count: int = 0
    semantic_source_item_count: int = 0
    semantic_claim_count: int = 0
    semantic_claim_source_fields: list[str] = field(default_factory=list)
    evidence_source_field_count: int = 0
    evidence_source_item_count: int = 0
    dto_mapper_key: str | None = None
    dto_mapper_status: str | None = None
    dto_mapper_failure_code: str | None = None
    provider_evidence_ref_count: int = 0
    private_candidate_count: int = 0
    public_candidate_count: int = 0
    candidate_output_ref_count: int = 0
    target_ref_resolved_count: int = 0
    target_ref_rejected_count: int = 0
    quote_resolution_success_count: int = 0
    quote_resolution_rejected_count: int = 0
    evidence_coercion_input_count: int = 0
    evidence_coercion_output_count: int = 0
    evidence_valid_count: int = 0
    evidence_rejected_count: int = 0
    evidence_rejection_codes: list[str] = field(default_factory=list)
    candidate_command_count: int = 0
    evidence_command_count: int = 0
    persistence_attempted: bool = False
    transaction_started: bool = False
    transaction_committed: bool = False
    transaction_rolled_back: bool = False
    asset_written_count: int = 0
    version_written_count: int = 0
    evidence_written_count: int = 0
    artifact_written_count: int = 0
    failure_boundary: str | None = None
    failure_code: str | None = None
    # CHG-057 provider output contract diagnostics (safe counters only).
    output_contract_id: str | None = None
    output_contract_version: str | None = None
    provider_output_mode: str | None = None
    strict_schema_enabled: bool | None = None
    exact_contract_status: str | None = None
    initial_contract_failure_code: str | None = None
    repair_allowed: bool | None = None
    repair_attempted: bool | None = None
    repair_count: int = 0
    repair_status: str | None = None
    repaired_contract_status: str | None = None
    dto_runtime_type: str | None = None
    dto_schema_id: str | None = None
    dto_validation_status: str | None = None
    schema_label_verified: bool | None = None
    undeclared_top_level_fields: list[str] = field(default_factory=list)
    evidence_id_resolved_count: int = 0
    # CHG-058 Citation Evidence Contract V2 (safe counters; no claim/citation bodies).
    evidence_contract_version: str | None = None
    citation_contract_version: str | None = None
    catalog_id: str | None = None
    catalog_entry_count: int = 0
    catalog_fingerprint: str | None = None
    prompt_catalog_fingerprint: str | None = None
    schema_catalog_fingerprint: str | None = None
    resolver_catalog_fingerprint: str | None = None
    catalog_fingerprints_match: bool | None = None
    observed_claim_count: int = 0
    inferred_claim_count: int = 0
    not_observed_claim_count: int = 0
    provider_citation_count: int = 0
    unique_provider_citation_count: int = 0
    citation_resolved_count: int = 0
    citation_rejected_count: int = 0
    stale_citation_count: int = 0
    unknown_citation_count: int = 0
    catalog_mismatch_count: int = 0
    locator_validation_count: int = 0
    locator_rejected_count: int = 0
    critical_claims_without_citation_count: int = 0
    persistence_complete: bool | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Defensive strip of any accidental long strings.
        for key, value in list(payload.items()):
            if isinstance(value, str) and len(value) > 256:
                payload[key] = value[:64] + "…"
            if key in {
                "prompt",
                "messages",
                "raw_response",
                "credential",
                "api_key",
                "body",
                "quote",
                "text",
            }:
                payload.pop(key, None)
        return payload


@dataclass
class CitationEvidencePipelineDiagnostics(LiveModulePipelineDiagnostics):
    """V2 citation evidence pipeline diagnostics (extends Live counters)."""

    rejection_codes: list[str] = field(default_factory=list)

    def to_safe_dict(self) -> dict[str, Any]:
        payload = super().to_safe_dict()
        # Prefer rejection_codes alias when V2 path populated it.
        if self.rejection_codes and not payload.get("evidence_rejection_codes"):
            payload["evidence_rejection_codes"] = list(self.rejection_codes)
        elif self.rejection_codes:
            payload["rejection_codes"] = list(self.rejection_codes)
        return payload


def fingerprint_structured_output(structured: Mapping[str, Any] | None) -> str | None:
    """Schema/shape fingerprint — keys + value types only, never claim text."""

    if not structured:
        return None

    def _shape(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): _shape(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if isinstance(value, (list, tuple)):
            return [_shape(value[0])] if value else []
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "string"
        return type(value).__name__

    blob = json.dumps(_shape(dict(structured)), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def infer_failure_boundary(diag: LiveModulePipelineDiagnostics) -> str | None:
    if diag.failure_boundary:
        return diag.failure_boundary
    if not diag.structured_output_present:
        return "PROVIDER_RESULT_EMPTY"
    if diag.dto_mapper_status == "rejected" or (
        diag.semantic_source_field_count >= 1 and diag.semantic_claim_count < 1
    ):
        return "PRIVATE_TRANSLATION_EMPTY"
    if diag.private_candidate_count < 1:
        return "PRIVATE_TRANSLATION_EMPTY"
    if diag.public_candidate_count < 1:
        return "PUBLIC_TRANSLATION_EMPTY"
    if diag.target_ref_rejected_count > 0 and diag.target_ref_resolved_count < 1:
        return "EVIDENCE_VALIDATION_REJECTED"
    if diag.quote_resolution_rejected_count > 0 and diag.quote_resolution_success_count < 1:
        return "EVIDENCE_VALIDATION_REJECTED"
    if (
        int(getattr(diag, "citation_rejected_count", 0) or 0) > 0
        and int(getattr(diag, "citation_resolved_count", 0) or 0) < 1
    ):
        return "EVIDENCE_VALIDATION_REJECTED"
    if diag.evidence_valid_count < 1 and diag.evidence_rejected_count > 0:
        return "EVIDENCE_VALIDATION_REJECTED"
    if diag.evidence_coercion_output_count < 1 and diag.provider_evidence_ref_count > 0:
        return "EVIDENCE_COERCION_EMPTY"
    if diag.candidate_command_count < 1:
        return "CANDIDATE_COMMAND_EMPTY"
    if diag.transaction_rolled_back:
        return "ORM_TRANSACTION_ROLLBACK"
    if diag.persistence_attempted and not diag.transaction_committed:
        return "ORM_TRANSACTION_ROLLBACK"
    return None


def merge_rejection_codes(codes: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for code in codes:
        token = str(code or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out
