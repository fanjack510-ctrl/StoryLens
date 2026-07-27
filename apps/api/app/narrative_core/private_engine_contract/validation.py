"""Module output validation pipeline contract (Phase 2B-P)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)

OUTPUT_VALIDATION_PIPELINE: tuple[str, ...] = (
    "provider_response",
    "json_schema_parse",
    "module_dto_validation",
    "reference_validation",
    "evidence_validation",
    "book_snapshot_isolation",
    "duplicate_detection",
    "conflict_candidate_detection",
    "candidate_asset_relation_build",
    "artifact_build",
    "result_projection",
)


@dataclass(frozen=True, slots=True)
class ModuleOutputValidationReport:
    schema_valid: bool
    references_valid: bool
    evidence_valid: bool
    snapshot_valid: bool
    duplicate_summary: Mapping[str, Any]
    conflict_summary: Mapping[str, Any]
    missing_fields: tuple[str, ...]
    invalid_refs: tuple[str, ...]
    evidence_coverage: Mapping[str, Any]
    warnings: tuple[str, ...]
    accepted: bool
    retry_recommended: bool
    error_code: str | None = None

    def __post_init__(self) -> None:
        # accepted=False means no candidate write.
        if self.accepted and not (
            self.schema_valid
            and self.references_valid
            and self.evidence_valid
            and self.snapshot_valid
        ):
            raise ValueError("accepted=True requires all core validations to pass")


@dataclass
class FakeModuleOutputValidator:
    """Rejects invalid schema/refs/insufficient evidence. No model calls."""

    budget_allows_retry: bool = True

    def validate(self, module_outputs: Mapping[str, Any]) -> ModuleOutputValidationReport:
        schema_valid = "schema_error" not in module_outputs
        references_valid = "invalid_ref" not in module_outputs
        evidence_valid = module_outputs.get("evidence_insufficient") is not True
        snapshot_valid = module_outputs.get("snapshot_mismatch") is not True

        error_code: str | None = None
        if not schema_valid:
            error_code = PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value
        elif not references_valid:
            error_code = PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value
        elif not evidence_valid:
            error_code = PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT.value
        elif not snapshot_valid:
            error_code = PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH.value

        accepted = schema_valid and references_valid and evidence_valid and snapshot_valid
        # Fake default outputs are markers only — not production-accepted candidates.
        if module_outputs.get("fake") is True and "force_accept" not in module_outputs:
            accepted = False
            error_code = error_code or PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT.value

        retry_recommended = (not accepted) and self.budget_allows_retry and error_code in {
            PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value,
            PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID.value,
        }

        return ModuleOutputValidationReport(
            schema_valid=schema_valid,
            references_valid=references_valid,
            evidence_valid=evidence_valid,
            snapshot_valid=snapshot_valid,
            duplicate_summary={},
            conflict_summary={},
            missing_fields=tuple(module_outputs.get("missing_fields", ())),
            invalid_refs=tuple(module_outputs.get("invalid_refs", ())),
            evidence_coverage=dict(module_outputs.get("evidence_coverage", {})),
            warnings=("fake_validator",) if module_outputs.get("fake") else (),
            accepted=accepted,
            retry_recommended=retry_recommended,
            error_code=error_code,
        )

    def reject_without_candidate_write(self, report: ModuleOutputValidationReport) -> None:
        if report.accepted:
            return
        if report.error_code:
            try:
                code = PrivateEngineErrorCode(report.error_code)
            except ValueError:
                return
            raise private_engine_error(code)
