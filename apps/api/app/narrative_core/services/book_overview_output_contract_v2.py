"""BookOverview Citation Evidence Contract V2 (CHG-058).

Formal Live output is flat BookOverviewResultV2 only.
Citation membership is validated against the request-bound CitationCatalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

OUTPUT_CONTRACT_ID = "BookOverviewResultV2"
OUTPUT_CONTRACT_VERSION = "2.0.0"
REPAIR_POLICY_ID = "book_overview.schema_and_citation_repair"
REPAIR_POLICY_VERSION = "1.0.0"
MAX_REPAIR_COUNT = 1
SCHEMA_ID = "BookOverviewResultV2"
SCHEMA_REF = "dto://BookOverviewResultV2"

BOOK_OVERVIEW_V2_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "contract_version",
        "logline",
        "premise",
        "central_question",
        "primary_conflict",
        "structure_summary",
        "ending_state",
        "overall_confidence",
    }
)

FAILURE_NOT_OBJECT = "STRUCTURED_OUTPUT_NOT_OBJECT"
FAILURE_UNDECLARED_TOP_LEVEL = "UNDECLARED_TOP_LEVEL_FIELDS"
FAILURE_MISSING_REQUIRED = "MISSING_REQUIRED_FIELDS"
FAILURE_DTO_VALIDATION = "DTO_VALIDATION_FAILED"
FAILURE_UNKNOWN_CITATION = "UNKNOWN_CITATION_ID"
FAILURE_STALE_CITATION = "STALE_CITATION_ID"
FAILURE_MISSING_REQUIRED_CITATION = "MISSING_REQUIRED_CITATION"  # deprecated umbrella
FAILURE_REQUIRED_CLAIM_NOT_OBSERVED = "REQUIRED_CLAIM_NOT_OBSERVED"
FAILURE_REQUIRED_CLAIM_VALUE_EMPTY = "REQUIRED_CLAIM_VALUE_EMPTY"
FAILURE_REQUIRED_CLAIM_CITATION_EMPTY = "REQUIRED_CLAIM_CITATION_EMPTY"
FAILURE_CLAIM_STATUS_CITATION_CONFLICT = "CLAIM_STATUS_CITATION_CONFLICT"
FAILURE_OPTIONAL_CLAIM_STATUS_INVALID = "OPTIONAL_CLAIM_STATUS_INVALID"
FAILURE_EXECUTION_CONTEXT_MISMATCH = "EXECUTION_CONTEXT_FINGERPRINT_MISMATCH"
FAILURE_REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"
STATUS_CONTRACT_VALIDATION_FAILED = "contract_validation_failed"
STATUS_CITATION_VALIDATION_FAILED = "citation_validation_failed"
STATUS_REPAIR_EXHAUSTED = "repair_exhausted"


@dataclass(frozen=True, slots=True)
class BookOverviewV2ContractValidation:
    ok: bool
    failure_code: str | None
    observed_top_level_fields: tuple[str, ...]
    undeclared_top_level_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    typed_payload: dict[str, Any] | None
    schema_id: str | None
    schema_label_verified: bool
    diagnostics: Mapping[str, Any]


def is_book_overview_v2_schema_bound(
    *,
    schema_ref: str | None = None,
    schema_title: Any = None,
) -> bool:
    ref = str(schema_ref or "")
    title = str(schema_title or "")
    return (
        "BookOverviewResultV2" in ref
        or ref.endswith("dto://BookOverviewResultV2")
        or title == "BookOverviewResultV2"
        or "BookOverviewResultV2" in title
    )


def provider_output_constraint_text_v2(
    *,
    citation_ids: Sequence[str] | None = None,
    policy_text: str | None = None,
) -> str:
    ids = list(citation_ids or ())
    # CHG-059: full catalog IDs — do not truncate to 12.
    enum_hint = ", ".join(ids) if ids else "(catalog citation_ids)"
    policy = policy_text or (
        "Core fields logline/premise/central_question/primary_conflict MUST be "
        "observed or inferred with ≥1 citation_id (never not_observed). "
        "structure_summary/ending_state follow server FieldRequirementPolicy."
    )
    return (
        f"Output contract: {OUTPUT_CONTRACT_ID}@{OUTPUT_CONTRACT_VERSION} "
        f"({SCHEMA_REF}, contract_version=v2). "
        "Return ONLY one flat BookOverviewResultV2 JSON object. "
        "Each claim is {value, status, citation_ids, confidence}. "
        f"{policy} "
        f"citation_ids must be chosen from the complete catalog ({len(ids)} ids): {enum_hint}. "
        "Do NOT wrap in book_overview. Do NOT include evidence_map. "
        "Do NOT include evidence_refs. Do NOT return Markdown fences."
    )


def repair_instruction_text_v2(
    *,
    failure_code: str,
    observed_fields: Sequence[str],
    citation_ids: Sequence[str] | None = None,
    failed_diagnostics: Sequence[Mapping[str, Any]] | None = None,
    passed_fields: Sequence[str] | None = None,
    policy_text: str | None = None,
    capabilities: Mapping[str, Any] | None = None,
) -> str:
    ids = list(citation_ids or ())
    enum_hint = ", ".join(ids) if ids else "(catalog citation_ids)"
    try:
        from storylens_private_engine.citation import (
            build_field_requirement_policy,
            derive_context_capabilities,
            targeted_repair_instruction,
        )

        caps_obj = None
        if capabilities:
            caps_obj = derive_context_capabilities(
                selected_chapter_orders=tuple(capabilities.get("selected_chapter_orders") or ()),
                all_chapter_orders=tuple(capabilities.get("all_chapter_orders") or ()),
                selected_paragraph_count=int(capabilities.get("selected_paragraph_count") or 0),
                batch_index=int(capabilities.get("batch_index") or 0),
                batch_count=int(capabilities.get("batch_count") or 1),
                full_book_default=bool(capabilities.get("full_book_coverage") or False),
            )
            # Prefer capability flags already computed.
            from storylens_private_engine.citation.field_policy import ContextCapabilities

            caps_obj = ContextCapabilities(
                can_assess_core_overview=bool(
                    capabilities.get("can_assess_core_overview", True)
                ),
                can_assess_structure_progression=bool(
                    capabilities.get("can_assess_structure_progression", False)
                ),
                can_assess_ending_state=bool(
                    capabilities.get("can_assess_ending_state", False)
                ),
                full_book_coverage=bool(capabilities.get("full_book_coverage", False)),
                batch_index=int(capabilities.get("batch_index") or 0),
                batch_count=int(capabilities.get("batch_count") or 1),
                selected_chapter_count=int(capabilities.get("selected_chapter_count") or 0),
                total_chapter_count=int(capabilities.get("total_chapter_count") or 0),
                covers_first_chapter=bool(capabilities.get("covers_first_chapter", False)),
                covers_last_chapter=bool(capabilities.get("covers_last_chapter", False)),
                structural_span_ratio=float(capabilities.get("structural_span_ratio") or 0.0),
            )
        policy = build_field_requirement_policy(caps_obj)
        return targeted_repair_instruction(
            policy=policy,
            failed_diagnostics=[dict(x) for x in (failed_diagnostics or ())],
            passed_fields=list(passed_fields or observed_fields),
            citation_ids=ids,
            failure_code=failure_code,
        )
    except Exception:  # noqa: BLE001
        return (
            f"Previous output failed V2 contract validation ({failure_code}). "
            f"Observed top-level fields: {', '.join(observed_fields) or '(none)'}. "
            "Regenerate a complete BookOverviewResultV2 JSON object only. "
            f"Use only these citation_ids ({len(ids)}): {enum_hint}. "
            + (policy_text or "Core fields require observed/inferred with citations.")
        )


def _try_private_validate(
    structured: Mapping[str, Any],
    *,
    catalog: Any,
    capabilities: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from storylens_private_engine.citation import validate_book_overview_result_v2
        from storylens_private_engine.citation.field_policy import ContextCapabilities
    except Exception:  # noqa: BLE001
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    # Public CitationCatalog exposes citation_ids as a @property (tuple);
    # private Catalog may expose a callable. Accept both.
    ids_attr = getattr(catalog, "citation_ids", None)
    if ids_attr is None:
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    if not callable(ids_attr) and not isinstance(ids_attr, (list, tuple)):
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    caps_obj = None
    if capabilities:
        try:
            caps_obj = ContextCapabilities(
                can_assess_core_overview=bool(
                    capabilities.get("can_assess_core_overview", True)
                ),
                can_assess_structure_progression=bool(
                    capabilities.get("can_assess_structure_progression", False)
                ),
                can_assess_ending_state=bool(
                    capabilities.get("can_assess_ending_state", False)
                ),
                full_book_coverage=bool(capabilities.get("full_book_coverage", False)),
                batch_index=int(capabilities.get("batch_index") or 0),
                batch_count=int(capabilities.get("batch_count") or 1),
                selected_chapter_count=int(capabilities.get("selected_chapter_count") or 0),
                total_chapter_count=int(capabilities.get("total_chapter_count") or 0),
                covers_first_chapter=bool(capabilities.get("covers_first_chapter", False)),
                covers_last_chapter=bool(capabilities.get("covers_last_chapter", False)),
                structural_span_ratio=float(capabilities.get("structural_span_ratio") or 0.0),
            )
        except Exception:  # noqa: BLE001
            caps_obj = None
    try:
        dto, err = validate_book_overview_result_v2(
            structured, catalog, capabilities=caps_obj
        )
    except TypeError:
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    if dto is None:
        return None, str(err or FAILURE_DTO_VALIDATION)
    if hasattr(dto, "model_dump"):
        return dict(dto.model_dump()), None
    return dict(structured), None


def _public_shape_validate(
    structured: Mapping[str, Any],
    *,
    allowed_citation_ids: Sequence[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Fallback shape/membership check when private validator is unavailable."""

    from app.narrative_core.product_contract.module_results import (
        BookOverviewResultV2,
        CitedClaimDto,
    )

    allowed = {str(x) for x in allowed_citation_ids}
    try:
        claims: dict[str, CitedClaimDto] = {}
        for field in (
            "logline",
            "premise",
            "central_question",
            "primary_conflict",
            "structure_summary",
            "ending_state",
        ):
            raw = structured.get(field)
            if not isinstance(raw, Mapping):
                return None, FAILURE_DTO_VALIDATION
            claim = CitedClaimDto(
                value=raw.get("value"),
                status=str(raw.get("status") or ""),
                citation_ids=tuple(str(x) for x in (raw.get("citation_ids") or ())),
                confidence=raw.get("confidence"),
            )
            for cid in claim.citation_ids:
                if cid not in allowed:
                    prefix = cid.split("-")[1] if cid.count("-") >= 2 else ""
                    allowed_prefixes = {
                        a.split("-")[1] for a in allowed if a.count("-") >= 2
                    }
                    if prefix and prefix not in allowed_prefixes:
                        return None, FAILURE_STALE_CITATION
                    return None, FAILURE_UNKNOWN_CITATION
            claims[field] = claim
        if str(structured.get("contract_version") or "") != "v2":
            return None, FAILURE_DTO_VALIDATION
        # FieldRequirementPolicy — default allows conditional not_observed when capability unknown.
        try:
            from storylens_private_engine.citation import (
                build_field_requirement_policy,
                collect_claim_diagnostics,
                first_failure_code,
                parse_citation_id,
            )
            from storylens_private_engine.citation.ids import bundle_hash_prefix

            policy = build_field_requirement_policy()
            # Infer catalog prefix from first allowed id when present.
            prefix = ""
            if allowed:
                sample = next(iter(allowed))
                parsed = parse_citation_id(sample)
                prefix = parsed[0] if parsed else ""
            diags = collect_claim_diagnostics(
                {k: claims[k] for k in claims},
                catalog_ids=list(allowed),
                catalog_prefix=prefix,
                policy=policy,
                parse_citation_id_fn=parse_citation_id,
            )
            fail = first_failure_code(diags)
            if fail:
                return None, fail
        except Exception:  # noqa: BLE001
            for field in (
                "logline",
                "premise",
                "central_question",
                "primary_conflict",
            ):
                if claims[field].status == "not_observed":
                    return None, FAILURE_REQUIRED_CLAIM_NOT_OBSERVED
        dto = BookOverviewResultV2(
            logline=claims["logline"],
            premise=claims["premise"],
            central_question=claims["central_question"],
            primary_conflict=claims["primary_conflict"],
            structure_summary=claims["structure_summary"],
            ending_state=claims["ending_state"],
            contract_version="v2",
            overall_confidence=structured.get("overall_confidence"),
        )
        return {
            "contract_version": dto.contract_version,
            "logline": {
                "value": dto.logline.value,
                "status": dto.logline.status,
                "citation_ids": list(dto.logline.citation_ids),
                "confidence": dto.logline.confidence,
            },
            "premise": {
                "value": dto.premise.value,
                "status": dto.premise.status,
                "citation_ids": list(dto.premise.citation_ids),
                "confidence": dto.premise.confidence,
            },
            "central_question": {
                "value": dto.central_question.value,
                "status": dto.central_question.status,
                "citation_ids": list(dto.central_question.citation_ids),
                "confidence": dto.central_question.confidence,
            },
            "primary_conflict": {
                "value": dto.primary_conflict.value,
                "status": dto.primary_conflict.status,
                "citation_ids": list(dto.primary_conflict.citation_ids),
                "confidence": dto.primary_conflict.confidence,
            },
            "structure_summary": {
                "value": dto.structure_summary.value,
                "status": dto.structure_summary.status,
                "citation_ids": list(dto.structure_summary.citation_ids),
                "confidence": dto.structure_summary.confidence,
            },
            "ending_state": {
                "value": dto.ending_state.value,
                "status": dto.ending_state.status,
                "citation_ids": list(dto.ending_state.citation_ids),
                "confidence": dto.ending_state.confidence,
            },
            "overall_confidence": dto.overall_confidence,
        }, None
    except Exception:  # noqa: BLE001
        return None, FAILURE_DTO_VALIDATION


def validate_book_overview_provider_output_v2(
    structured: Any,
    *,
    catalog: Any | None = None,
    allowed_citation_ids: Sequence[str] | None = None,
    capabilities: Mapping[str, Any] | None = None,
) -> BookOverviewV2ContractValidation:
    """Exact top-level + V2 DTO/citation validation. Never unwraps wrappers."""

    diag: dict[str, Any] = {
        "output_contract_id": OUTPUT_CONTRACT_ID,
        "output_contract_version": OUTPUT_CONTRACT_VERSION,
        "dto_schema_id": SCHEMA_ID,
        "dto_validation_status": "PENDING",
        "schema_label_verified": False,
        "exact_contract_status": "PENDING",
        "evidence_contract_version": "v2",
    }
    if not isinstance(structured, Mapping):
        return BookOverviewV2ContractValidation(
            ok=False,
            failure_code=FAILURE_NOT_OBJECT,
            observed_top_level_fields=(),
            undeclared_top_level_fields=(),
            missing_required_fields=(),
            typed_payload=None,
            schema_id=None,
            schema_label_verified=False,
            diagnostics={
                **diag,
                "exact_contract_status": "FAILED",
                "dto_validation_status": "FAILED",
                "failure_code": FAILURE_NOT_OBJECT,
            },
        )

    observed = tuple(sorted(str(k) for k in structured.keys()))
    undeclared = tuple(
        sorted(k for k in observed if k not in BOOK_OVERVIEW_V2_ALLOWED_TOP_LEVEL)
    )
    diag["observed_top_level_fields"] = list(observed)
    diag["undeclared_top_level_fields"] = list(undeclared)
    if undeclared:
        return BookOverviewV2ContractValidation(
            ok=False,
            failure_code=FAILURE_UNDECLARED_TOP_LEVEL,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=undeclared,
            missing_required_fields=(),
            typed_payload=None,
            schema_id=None,
            schema_label_verified=False,
            diagnostics={
                **diag,
                "exact_contract_status": "FAILED",
                "dto_validation_status": "FAILED",
                "failure_code": FAILURE_UNDECLARED_TOP_LEVEL,
            },
        )

    required = (
        "contract_version",
        "logline",
        "premise",
        "central_question",
        "primary_conflict",
        "structure_summary",
        "ending_state",
    )
    missing = tuple(name for name in required if name not in structured)
    if missing:
        return BookOverviewV2ContractValidation(
            ok=False,
            failure_code=FAILURE_MISSING_REQUIRED,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=(),
            missing_required_fields=missing,
            typed_payload=None,
            schema_id=None,
            schema_label_verified=False,
            diagnostics={
                **diag,
                "exact_contract_status": "FAILED",
                "dto_validation_status": "FAILED",
                "failure_code": FAILURE_MISSING_REQUIRED,
                "missing_required_fields": list(missing),
            },
        )

    allowed = list(allowed_citation_ids or ())
    if catalog is not None:
        getter = getattr(catalog, "citation_ids", None)
        if callable(getter):
            allowed = list(getter())
        elif isinstance(getter, (list, tuple)):
            allowed = list(getter)

    typed: dict[str, Any] | None = None
    err: str | None = None
    if catalog is not None:
        typed, err = _try_private_validate(
            structured, catalog=catalog, capabilities=capabilities
        )
    if typed is None and err in {None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"}:
        typed, err = _public_shape_validate(structured, allowed_citation_ids=allowed)

    if typed is None:
        return BookOverviewV2ContractValidation(
            ok=False,
            failure_code=str(err or FAILURE_DTO_VALIDATION),
            observed_top_level_fields=observed,
            undeclared_top_level_fields=(),
            missing_required_fields=(),
            typed_payload=None,
            schema_id=None,
            schema_label_verified=False,
            diagnostics={
                **diag,
                "exact_contract_status": "FAILED",
                "dto_validation_status": "FAILED",
                "failure_code": str(err or FAILURE_DTO_VALIDATION),
            },
        )

    return BookOverviewV2ContractValidation(
        ok=True,
        failure_code=None,
        observed_top_level_fields=observed,
        undeclared_top_level_fields=(),
        missing_required_fields=(),
        typed_payload=typed,
        schema_id=SCHEMA_ID,
        schema_label_verified=True,
        diagnostics={
            **diag,
            "exact_contract_status": "SUCCESS",
            "dto_validation_status": "SUCCESS",
            "schema_label_verified": True,
            "dto_runtime_type": "BookOverviewResultV2",
        },
    )


def book_overview_result_v2_json_schema(
    *,
    citation_ids: Sequence[str] | None = None,
    catalog: Any | None = None,
) -> dict[str, Any]:
    """JSON Schema for Live binding. Prefer private dynamic schema when available."""

    if catalog is not None:
        try:
            from storylens_private_engine.citation import book_overview_result_v2_json_schema as _priv

            return dict(_priv(catalog))
        except Exception:  # noqa: BLE001
            pass

    ids = list(citation_ids or ())
    claim = {
        "type": "object",
        "properties": {
            "value": {"type": ["string", "null"]},
            "status": {
                "type": "string",
                "enum": ["observed", "inferred", "not_observed"],
            },
            "citation_ids": {
                "type": "array",
                "items": {"type": "string", **({"enum": ids} if ids else {})},
            },
            "confidence": {"type": ["number", "null"]},
        },
        "required": ["value", "status", "citation_ids"],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": SCHEMA_ID,
        "type": "object",
        "properties": {
            "contract_version": {"type": "string", "const": "v2"},
            "logline": claim,
            "premise": claim,
            "central_question": claim,
            "primary_conflict": claim,
            "structure_summary": claim,
            "ending_state": claim,
            "overall_confidence": {"type": ["number", "null"]},
        },
        "required": [
            "contract_version",
            "logline",
            "premise",
            "central_question",
            "primary_conflict",
            "structure_summary",
            "ending_state",
        ],
        "additionalProperties": False,
        "x_storylens_contract_id": OUTPUT_CONTRACT_ID,
        "x_storylens_contract_version": OUTPUT_CONTRACT_VERSION,
        "x_storylens_schema_ref": SCHEMA_REF,
        "x_storylens": {
            "citation_enum_count": len(ids),
            "evidence_contract_version": "v2",
        },
    }
