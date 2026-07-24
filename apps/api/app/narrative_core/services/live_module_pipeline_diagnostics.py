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
    claim_count: int = 0
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
    if diag.private_candidate_count < 1:
        return "PRIVATE_TRANSLATION_EMPTY"
    if diag.public_candidate_count < 1:
        return "PUBLIC_TRANSLATION_EMPTY"
    if diag.target_ref_rejected_count > 0 and diag.target_ref_resolved_count < 1:
        return "EVIDENCE_VALIDATION_REJECTED"
    if diag.quote_resolution_rejected_count > 0 and diag.quote_resolution_success_count < 1:
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
