"""Default Module Output Validator (Phase 2B Agent R / CHG-039).

Ordered pipeline: Schema → DTO → Reference → Evidence → Book/Snapshot →
Duplicate → Conflict → Accepted.

Depends on EvidenceValidator Protocol. Unit tests keep FakeEvidenceValidator;
Phase 2B Integration injects Agent Q DefaultEvidenceValidator via
DefaultEvidenceValidatorRuntimeAdapter. No ORM writes; no full raw response storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from app.narrative_core.enums import WholeBookModuleKey
from app.narrative_core.private_engine_contract.errors import PrivateEngineErrorCode
from app.narrative_core.private_engine_contract.evidence import (
    EvidenceCandidate,
    EvidenceValidationContext,
    EvidenceValidationReport,
    build_coverage_report,
    validate_evidence_candidates,
)
from app.narrative_core.private_engine_contract.module_spec import get_module_spec
from app.narrative_core.private_engine_contract.validation import (
    OUTPUT_VALIDATION_PIPELINE,
    ModuleOutputValidationReport,
)
from app.narrative_core.product_contract.module_results import (
    MODULE_RESULT_DTO_BY_KEY,
    assert_payload_keys_for_module,
)


@runtime_checkable
class EvidenceValidator(Protocol):
    """Protocol surface for Agent Q wiring; Fake fixture satisfies this."""

    def validate(
        self,
        candidates: Sequence[EvidenceCandidate],
        ctx: EvidenceValidationContext,
    ) -> EvidenceValidationReport: ...


@dataclass
class FakeEvidenceValidator:
    """Contract fixture — uses Phase 2B-P pure validation helpers."""

    def validate(
        self,
        candidates: Sequence[EvidenceCandidate],
        ctx: EvidenceValidationContext,
    ) -> EvidenceValidationReport:
        return validate_evidence_candidates(candidates, ctx)


@dataclass(frozen=True, slots=True)
class ReferenceResolver:
    """Known asset/entity/output refs available to the module input."""

    asset_ids: frozenset[int] = field(default_factory=frozenset)
    entity_ids: frozenset[int] = field(default_factory=frozenset)
    storyline_ids: frozenset[int] = field(default_factory=frozenset)
    chapter_ids: frozenset[int] = field(default_factory=frozenset)
    output_refs: frozenset[str] = field(default_factory=frozenset)
    known_fields_allow_unknown: bool = False


@dataclass(frozen=True, slots=True)
class ModuleOutputValidationInput:
    module_key: WholeBookModuleKey | str
    module_outputs: Mapping[str, Any]
    evidence_candidates: Sequence[EvidenceCandidate] = ()
    book_id: int = 1
    book_snapshot_id: int = 1
    expected_book_id: int | None = None
    expected_book_snapshot_id: int | None = None
    resolver: ReferenceResolver = field(default_factory=ReferenceResolver)
    evidence_ctx: EvidenceValidationContext | None = None
    prior_output_fingerprints: frozenset[str] = field(default_factory=frozenset)
    current_output_fingerprint: str | None = None
    conflict_markers: Sequence[str] = ()
    retry_policy_allows: bool = True
    require_evidence_for_acceptance: bool = True
    unknown_field_policy: str = "reject"  # reject | ignore (version strategy)


def _as_module_key(module_key: WholeBookModuleKey | str) -> WholeBookModuleKey:
    return module_key if isinstance(module_key, WholeBookModuleKey) else WholeBookModuleKey(module_key)


def _dto_field_names(module_key: WholeBookModuleKey) -> frozenset[str]:
    dto_cls = MODULE_RESULT_DTO_BY_KEY[module_key]
    return frozenset(f.name for f in fields(dto_cls))


def _collect_refs_from_outputs(module_outputs: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in (
        "protagonist_asset_id",
        "major_storyline_ids",
        "primary_storyline_ids",
        "character_focus_ids",
        "involved_entity_ids",
        "key_event_ids",
        "relation_ids",
        "storyline_asset_id",
        "hook_ids",
        "payoff_ids",
    ):
        value = module_outputs.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            refs.extend(f"{key}:{v}" for v in value)
        else:
            refs.append(f"{key}:{value}")
    for er in module_outputs.get("evidence_refs", ()) or ():
        if is_dataclass(er) and not isinstance(er, type):
            refs.append(f"evidence:{getattr(er, 'evidence_id', er)}")
        elif isinstance(er, Mapping):
            refs.append(f"evidence:{er.get('evidence_id')}")
        else:
            refs.append(f"evidence:{er}")
    return refs


@dataclass
class DefaultModuleOutputValidator:
    """Production-shaped validator used by Fake runners and future real engines."""

    evidence_validator: EvidenceValidator = field(default_factory=FakeEvidenceValidator)
    pipeline: tuple[str, ...] = OUTPUT_VALIDATION_PIPELINE
    # Thin hook for private module_extra supplements (CHG-043); proprietary rules stay private.
    module_extra_hook: Any | None = None

    def set_module_extra_hook(self, hook: Any | None) -> None:
        self.module_extra_hook = hook

    def validate(self, inp: ModuleOutputValidationInput) -> ModuleOutputValidationReport:
        module_key = _as_module_key(inp.module_key)
        spec = get_module_spec(module_key)
        warnings: list[str] = []
        missing_fields: list[str] = []
        invalid_refs: list[str] = []
        duplicate_summary: dict[str, Any] = {"count": 0, "fingerprints": []}
        conflict_summary: dict[str, Any] = {"count": 0, "markers": []}
        error_code: str | None = None

        # 1) Schema parse / presence
        schema_valid = True
        outputs = dict(inp.module_outputs)
        if outputs.get("schema_error") is True:
            schema_valid = False
            error_code = PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value
        if "dto" in outputs and not isinstance(outputs["dto"], Mapping):
            schema_valid = False
            error_code = PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value

        # Prefer nested dto payload when present.
        dto_payload = outputs.get("dto") if isinstance(outputs.get("dto"), Mapping) else outputs

        # 2) Module DTO validation
        try:
            assert_payload_keys_for_module(module_key, dict(dto_payload))
        except ValueError as exc:
            schema_valid = False
            missing_fields.extend(str(exc).split(":")[-1].strip(" []").replace("'", "").split(", "))
            error_code = error_code or PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value

        allowed = _dto_field_names(module_key)
        # Meta markers allowed alongside DTO fields in runner envelopes.
        meta_allowed = {
            "fake",
            "synthetic",
            "non_production",
            "partial",
            "unknown",
            "schema_error",
            "invalid_ref",
            "evidence_insufficient",
            "snapshot_mismatch",
            "cross_book",
            "duplicate",
            "conflict",
            "force_accept",
            "dto",
            "module_key",
            "module_version",
            "output_locale",
            "source_language",
            "fixture_id",
            "production",
            "empty_dto",
            "evidence_coverage",
            "missing_fields",
            "invalid_refs",
            "prompt_pack_version",
            "status_markers",
            "book_id",
            "book_snapshot_id",
            "configuration_fingerprint",
            "skip_provider",
            "asset_candidates",
            "relation_candidates",
            "conflict_candidates",
            "resolver_asset_ids",
            "resolver_entity_ids",
            "resolver_storyline_ids",
            "resolver_chapter_ids",
            "resolver_output_refs",
            "required_claims",
            "evidenced_claims",
            "resume_deduped",
            "overview_mode",
            "structure_mode",
            "chapter_mode",
            "storyline_type",
            "status",
            # Private Lab / private-engine adapter markers (non-DTO).
            "private_adapter",
            "private_engine",
            "private_module_adapter",
            "engine_id",
            "engine_version",
            "coverage",
            "credential_read",
            "direct_provider_http",
            "orm_access",
            "force_three_act",
            "prompt_pack_id",
            "allow_unknown_or_multiple_protagonists",
            "force_single_protagonist",
            "protagonist_asset_ids",
            "required_claims_refs",
            "evidenced_claims_refs",
            "evidence_candidates",
            "accepted",
        }
        unknown_fields = [
            k for k in dto_payload.keys() if k not in allowed and k not in meta_allowed
        ]
        if unknown_fields:
            if inp.unknown_field_policy == "reject":
                schema_valid = False
                error_code = error_code or PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value
                warnings.append(f"unknown_fields_rejected:{','.join(sorted(unknown_fields))}")
            else:
                warnings.append(f"unknown_fields_ignored:{','.join(sorted(unknown_fields))}")

        # 3) Reference validation
        references_valid = True
        if outputs.get("invalid_ref") is True or outputs.get("cross_book") is True:
            references_valid = False
            invalid_refs.append("marked_invalid_ref")
            error_code = error_code or PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value

        resolver = inp.resolver
        for key, value in dto_payload.items():
            if key.endswith("_asset_id") and value is not None:
                try:
                    asset_id = int(value)
                except (TypeError, ValueError):
                    references_valid = False
                    invalid_refs.append(f"{key}:{value}")
                    continue
                if resolver.asset_ids and asset_id not in resolver.asset_ids:
                    references_valid = False
                    invalid_refs.append(f"{key}:{asset_id}")
            if key in {"major_storyline_ids", "primary_storyline_ids"} and value:
                for sid in value:
                    if resolver.storyline_ids and int(sid) not in resolver.storyline_ids:
                        references_valid = False
                        invalid_refs.append(f"{key}:{sid}")
            if key in {"character_focus_ids", "involved_entity_ids"} and value:
                for eid in value:
                    if resolver.entity_ids and int(eid) not in resolver.entity_ids:
                        references_valid = False
                        invalid_refs.append(f"{key}:{eid}")
            if key == "chapter_id" and value is not None:
                if resolver.chapter_ids and int(value) not in resolver.chapter_ids:
                    references_valid = False
                    invalid_refs.append(f"chapter_id:{value}")

        if not references_valid:
            error_code = error_code or PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value

        # 4) Evidence validation
        evidence_ctx = inp.evidence_ctx or EvidenceValidationContext(
            book_id=inp.expected_book_id or inp.book_id,
            book_snapshot_id=inp.expected_book_snapshot_id or inp.book_snapshot_id,
            known_output_refs=resolver.output_refs,
            chapter_ids=resolver.chapter_ids,
            paragraph_ids=frozenset(),
        )
        evidence_report = self.evidence_validator.validate(tuple(inp.evidence_candidates), evidence_ctx)
        evidence_valid = evidence_report.valid
        if outputs.get("evidence_insufficient") is True:
            evidence_valid = False
        if inp.require_evidence_for_acceptance and spec.key_claims_require_evidence:
            if not inp.evidence_candidates and not outputs.get("partial") and not outputs.get("empty_dto"):
                evidence_valid = False
                warnings.append("key_claims_require_evidence")
        if not evidence_valid:
            error_code = error_code or PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT.value

        required_claims = int(outputs.get("required_claims", 1 if inp.evidence_candidates else 0) or 0)
        evidenced_claims = int(
            outputs.get("evidenced_claims", len(inp.evidence_candidates) if evidence_valid else 0) or 0
        )
        coverage = build_coverage_report(
            module_key=module_key.value,
            required_claims=max(required_claims, 0),
            evidenced_claims=max(evidenced_claims, 0),
            missing_target_refs=tuple(invalid_refs),
        )
        if coverage.incomplete and inp.require_evidence_for_acceptance and not outputs.get("partial"):
            evidence_valid = False
            error_code = error_code or PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT.value

        # 5) Book / Snapshot isolation
        snapshot_valid = True
        expected_book = inp.expected_book_id if inp.expected_book_id is not None else inp.book_id
        expected_snap = (
            inp.expected_book_snapshot_id
            if inp.expected_book_snapshot_id is not None
            else inp.book_snapshot_id
        )
        if outputs.get("snapshot_mismatch") is True:
            snapshot_valid = False
        if inp.book_id != expected_book or outputs.get("cross_book") is True:
            snapshot_valid = False
            references_valid = False
            invalid_refs.append("cross_book")
            error_code = error_code or PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value
        if inp.book_snapshot_id != expected_snap:
            snapshot_valid = False
            error_code = error_code or PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH.value
        for candidate in inp.evidence_candidates:
            if candidate.book_snapshot_id != expected_snap:
                snapshot_valid = False
                error_code = error_code or PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH.value
            if candidate.book_id is not None and candidate.book_id != expected_book:
                snapshot_valid = False
                references_valid = False
                invalid_refs.append(f"evidence_cross_book:{candidate.candidate_id}")

        # 6) Duplicate detection
        if outputs.get("duplicate") is True or (
            inp.current_output_fingerprint
            and inp.current_output_fingerprint in inp.prior_output_fingerprints
        ):
            duplicate_summary = {
                "count": 1,
                "fingerprints": [inp.current_output_fingerprint or "duplicate"],
            }
            warnings.append("duplicate_detected")

        # 7) Conflict detection
        markers = list(inp.conflict_markers)
        if outputs.get("conflict") is True:
            markers.append("output_conflict_marker")
        if markers:
            conflict_summary = {"count": len(markers), "markers": markers}
            warnings.append("conflict_detected")

        # 8) Accepted
        accepted = schema_valid and references_valid and evidence_valid and snapshot_valid
        if outputs.get("empty_dto") is True and outputs.get("force_accept") is not True:
            accepted = False
            warnings.append("empty_dto_not_accepted")
            error_code = error_code or PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value
        if outputs.get("fake") is True and outputs.get("force_accept") is not True:
            # Fake/synthetic outputs are never production-accepted unless explicitly forced in tests.
            accepted = False
            warnings.append("fake_output_not_production_accepted")
            error_code = error_code or PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT.value

        # Optional private module_extra supplements (thin public hook only).
        if self.module_extra_hook is not None and hasattr(self.module_extra_hook, "validate"):
            extra = self.module_extra_hook.validate(module_key.value, outputs)
            if isinstance(extra, Mapping):
                if extra.get("schema_valid") is False:
                    schema_valid = False
                    accepted = False
                if extra.get("references_valid") is False:
                    references_valid = False
                    accepted = False
                if extra.get("evidence_valid") is False and outputs.get("partial") is not True:
                    evidence_valid = False
                    accepted = False
                for note in extra.get("notes") or ():
                    warnings.append(str(note))

        if not accepted and error_code is None:
            error_code = PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT.value

        retry_recommended = (
            (not accepted)
            and inp.retry_policy_allows
            and error_code
            in {
                PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value,
                PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID.value,
            }
        )

        # Never persist full raw response in report.
        if "raw_response" in outputs:
            warnings.append("raw_response_stripped")

        return ModuleOutputValidationReport(
            schema_valid=schema_valid,
            references_valid=references_valid,
            evidence_valid=evidence_valid,
            snapshot_valid=snapshot_valid,
            duplicate_summary=duplicate_summary,
            conflict_summary=conflict_summary,
            missing_fields=tuple(f for f in missing_fields if f),
            invalid_refs=tuple(sorted(set(invalid_refs))),
            evidence_coverage={
                "required_claims": coverage.required_claims,
                "evidenced_claims": coverage.evidenced_claims,
                "coverage_ratio": coverage.coverage_ratio,
                "incomplete": coverage.incomplete,
                "collected_refs": _collect_refs_from_outputs(dto_payload),
            },
            warnings=tuple(warnings),
            accepted=accepted,
            retry_recommended=retry_recommended,
            error_code=error_code if not accepted else None,
        )


__all__ = [
    "DefaultModuleOutputValidator",
    "EvidenceValidator",
    "FakeEvidenceValidator",
    "ModuleOutputValidationInput",
    "ReferenceResolver",
]
