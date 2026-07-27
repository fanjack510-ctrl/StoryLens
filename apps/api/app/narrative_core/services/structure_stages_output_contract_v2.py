"""StructureStages Citation Evidence Contract V2 (CHG-20260725-001).

Formal Live output is flat StructureStagesResultV2 only.
Citation membership is validated against the request-bound CitationCatalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

OUTPUT_CONTRACT_ID = "StructureStagesResultV2"
OUTPUT_CONTRACT_VERSION = "2.0.0"
REPAIR_POLICY_ID = "structure_stages.schema_and_citation_repair"
REPAIR_POLICY_VERSION = "1.0.0"
MAX_REPAIR_COUNT = 1
SCHEMA_ID = "StructureStagesResultV2"
SCHEMA_REF = "dto://StructureStagesResultV2"

STRUCTURE_STAGES_V2_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "contract_version",
        "evidence_contract_version",
        "coverage_scope",
        "context_capabilities",
        "stages",
        "turning_points",
        "analysis_confidence",
        "overall_confidence",  # public alias accepted then normalized by private
        "limitations",
    }
)

FAILURE_NOT_OBJECT = "STRUCTURED_OUTPUT_NOT_OBJECT"
FAILURE_UNDECLARED_TOP_LEVEL = "UNDECLARED_TOP_LEVEL_FIELDS"
FAILURE_MISSING_REQUIRED = "MISSING_REQUIRED_FIELDS"
FAILURE_DTO_VALIDATION = "DTO_VALIDATION_FAILED"
FAILURE_UNKNOWN_CITATION = "UNKNOWN_CITATION_ID"
FAILURE_STALE_CITATION = "STALE_CITATION_ID"
FAILURE_REQUIRED_CLAIM_NOT_OBSERVED = "REQUIRED_CLAIM_NOT_OBSERVED"
FAILURE_REQUIRED_CLAIM_VALUE_EMPTY = "REQUIRED_CLAIM_VALUE_EMPTY"
FAILURE_REQUIRED_CLAIM_CITATION_EMPTY = "REQUIRED_CLAIM_CITATION_EMPTY"
FAILURE_STAGE_SUMMARY_CITATION_EMPTY = "STRUCTURE_STAGE_SUMMARY_CITATION_EMPTY"
FAILURE_STAGE_START_BOUNDARY_MISSING = "STRUCTURE_STAGE_START_BOUNDARY_MISSING"
FAILURE_STAGE_END_BOUNDARY_MISSING = "STRUCTURE_STAGE_END_BOUNDARY_MISSING"
FAILURE_TP_CITATION_EMPTY = "TURNING_POINT_CITATION_EMPTY"
FAILURE_STAGE_RANGE_OVERLAP = "STRUCTURE_STAGE_RANGE_OVERLAP"
FAILURE_STAGE_RANGE_NON_CONTIGUOUS = "STRUCTURE_STAGE_RANGE_NON_CONTIGUOUS"
FAILURE_COVERAGE_SCOPE_INVALID = "STRUCTURE_COVERAGE_SCOPE_INVALID"
FAILURE_LOCAL_REF_DUPLICATE = "STRUCTURE_LOCAL_REF_DUPLICATE"
FAILURE_LOCAL_REF_UNKNOWN = "STRUCTURE_LOCAL_REF_UNKNOWN"
FAILURE_EXECUTION_CONTEXT_MISMATCH = "EXECUTION_CONTEXT_FINGERPRINT_MISMATCH"
FAILURE_REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"
STATUS_CONTRACT_VALIDATION_FAILED = "contract_validation_failed"
STATUS_CITATION_VALIDATION_FAILED = "citation_validation_failed"
STATUS_REPAIR_EXHAUSTED = "repair_exhausted"


@dataclass(frozen=True, slots=True)
class StructureStagesV2ContractValidation:
    ok: bool
    failure_code: str | None
    observed_top_level_fields: tuple[str, ...]
    undeclared_top_level_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    typed_payload: dict[str, Any] | None
    schema_id: str | None
    schema_label_verified: bool
    diagnostics: Mapping[str, Any]


def is_structure_stages_v2_schema_bound(
    *,
    schema_ref: str | None = None,
    schema_title: Any = None,
) -> bool:
    ref = str(schema_ref or "")
    title = str(schema_title or "")
    return (
        "StructureStagesResultV2" in ref
        or ref.endswith("dto://StructureStagesResultV2")
        or title == "StructureStagesResultV2"
        or "StructureStagesResultV2" in title
    )


def provider_output_constraint_text_v2(
    *,
    citation_ids: Sequence[str] | None = None,
    policy_text: str | None = None,
) -> str:
    ids = list(citation_ids or ())
    enum_hint = ", ".join(ids) if ids else "(catalog citation_ids)"
    policy = policy_text or (
        "When stages exist: each stage.summary MUST be observed|inferred with ≥1 "
        "citation_id; start_boundary and end_boundary MUST each carry ≥1 citation_id. "
        "Turning points are parallel to stages. Variable stage count; never force 3/5-act."
    )
    return (
        f"Output contract: {OUTPUT_CONTRACT_ID}@{OUTPUT_CONTRACT_VERSION} "
        f"({SCHEMA_REF}, contract_version=v2). "
        "Return ONLY one flat StructureStagesResultV2 JSON object with parallel "
        "stages[] and turning_points[]. "
        f"{policy} "
        f"citation_ids must be chosen from the complete catalog ({len(ids)} ids): {enum_hint}. "
        "Do NOT wrap in structure_stages. Do NOT include evidence_map. "
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
        from storylens_private_engine.citation.structure_field_policy import (
            build_structure_field_requirement_policy,
            derive_structure_context_capabilities,
        )

        caps_obj = None
        if capabilities:
            caps_obj = derive_structure_context_capabilities(
                selected_chapter_orders=tuple(
                    capabilities.get("selected_chapter_orders") or ()
                ),
                all_chapter_orders=tuple(capabilities.get("all_chapter_orders") or ()),
                selected_paragraph_count=int(
                    capabilities.get("selected_paragraph_count") or 0
                ),
                batch_index=int(capabilities.get("batch_index") or 0),
                batch_count=int(capabilities.get("batch_count") or 1),
                full_book_default=bool(
                    capabilities.get("is_full_book_coverage")
                    or capabilities.get("full_book_coverage")
                    or False
                ),
            )
        policy = build_structure_field_requirement_policy(caps_obj)
        # Prefer private targeted repair when available.
        try:
            from storylens_private_engine.citation import targeted_repair_instruction

            return targeted_repair_instruction(
                policy=policy,
                failed_diagnostics=[dict(x) for x in (failed_diagnostics or ())],
                passed_fields=list(passed_fields or observed_fields),
                citation_ids=ids,
                failure_code=failure_code,
            )
        except Exception:  # noqa: BLE001
            return (
                f"Previous output failed Structure V2 contract ({failure_code}). "
                f"Observed top-level fields: {', '.join(observed_fields) or '(none)'}. "
                "Regenerate a complete StructureStagesResultV2 JSON object only. "
                f"Use only these citation_ids ({len(ids)}): {enum_hint}. "
                + (policy_text or policy.prompt_rules_text())
            )
    except Exception:  # noqa: BLE001
        return (
            f"Previous output failed V2 contract validation ({failure_code}). "
            f"Observed top-level fields: {', '.join(observed_fields) or '(none)'}. "
            "Regenerate a complete StructureStagesResultV2 JSON object only. "
            f"Use only these citation_ids ({len(ids)}): {enum_hint}. "
            + (
                policy_text
                or "Stage summary/boundaries and TP descriptions require catalog citations."
            )
        )


def _claim_dict(claim: Any) -> dict[str, Any]:
    return {
        "value": claim.value,
        "status": claim.status,
        "citation_ids": list(claim.citation_ids),
        "confidence": claim.confidence,
    }


def _boundary_dict(boundary: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"citation_ids": list(boundary.citation_ids)}
    if boundary.value is not None:
        out["value"] = boundary.value
    if boundary.status is not None:
        out["status"] = boundary.status
    if boundary.confidence is not None:
        out["confidence"] = boundary.confidence
    return out


def _parse_chapter_range(raw: Any) -> tuple[int | None, int | None]:
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        start = None if raw[0] in (None, "") else int(raw[0])
        end = None if raw[1] in (None, "") else int(raw[1])
        return start, end
    return None, None


def _citation_allowed(cid: str, allowed: set[str]) -> str | None:
    if cid in allowed:
        return None
    prefix = cid.split("-")[1] if cid.count("-") >= 2 else ""
    allowed_prefixes = {a.split("-")[1] for a in allowed if a.count("-") >= 2}
    if prefix and prefix not in allowed_prefixes:
        return FAILURE_STALE_CITATION
    return FAILURE_UNKNOWN_CITATION


def _validate_stage_ranges(
    stages: Sequence[Mapping[str, Any]],
) -> str | None:
    """Reject overlapping or non-contiguous ordered chapter ranges when both ends set."""

    ranges: list[tuple[int, int, str]] = []
    for stage in stages:
        if not isinstance(stage, Mapping):
            continue
        start, end = _parse_chapter_range(stage.get("chapter_range"))
        key = str(stage.get("stage_key") or stage.get("local_ref") or "?")
        if start is None or end is None:
            continue
        if end < start:
            return FAILURE_STAGE_RANGE_NON_CONTIGUOUS
        ranges.append((start, end, key))
    if len(ranges) < 2:
        return None
    ranges.sort(key=lambda x: (x[0], x[1]))
    for i in range(len(ranges) - 1):
        a_start, a_end, _a = ranges[i]
        b_start, b_end, _b = ranges[i + 1]
        if b_start <= a_end:
            return FAILURE_STAGE_RANGE_OVERLAP
        if b_start > a_end + 1:
            return FAILURE_STAGE_RANGE_NON_CONTIGUOUS
        _ = b_end
        _ = a_start
    return None


from app.narrative_core.services.citation_catalog_v2 import catalog_for_private_engine

_catalog_for_private_engine = catalog_for_private_engine


def resolve_structure_context_capabilities(
    capabilities: Mapping[str, Any] | Any | None,
) -> Any | None:
    """Build private StructureContextCapabilities from binding/meta dict."""

    if capabilities is None:
        return None
    try:
        from storylens_private_engine.citation.structure_field_policy import (
            SELECTION_POLICY_VERSION,
            StructureContextCapabilities,
            derive_structure_context_capabilities,
        )
    except Exception:  # noqa: BLE001
        return None
    if isinstance(capabilities, StructureContextCapabilities):
        return capabilities
    if not isinstance(capabilities, Mapping):
        return None
    if "can_identify_span_stages" in capabilities:
        try:
            return StructureContextCapabilities(
                can_identify_local_stages=bool(
                    capabilities.get("can_identify_local_stages")
                ),
                can_identify_span_stages=bool(
                    capabilities.get("can_identify_span_stages")
                ),
                can_identify_turning_points=bool(
                    capabilities.get("can_identify_turning_points", True)
                ),
                can_assess_ending_stage=bool(
                    capabilities.get("can_assess_ending_stage")
                ),
                is_full_book_coverage=bool(
                    capabilities.get("is_full_book_coverage")
                ),
                has_beginning_window=bool(
                    capabilities.get("has_beginning_window")
                ),
                has_middle_window=bool(capabilities.get("has_middle_window")),
                has_ending_window=bool(capabilities.get("has_ending_window")),
                selection_policy_version=str(
                    capabilities.get("selection_policy_version")
                    or SELECTION_POLICY_VERSION
                ),
                batch_index=int(capabilities.get("batch_index") or 0),
                batch_count=int(capabilities.get("batch_count") or 1),
                selected_chapter_count=int(
                    capabilities.get("selected_chapter_count") or 0
                ),
                total_chapter_count=int(
                    capabilities.get("total_chapter_count") or 0
                ),
                selected_paragraph_count=int(
                    capabilities.get("selected_paragraph_count") or 0
                ),
                structural_span_ratio=float(
                    capabilities.get("structural_span_ratio") or 0.0
                ),
            )
        except Exception:  # noqa: BLE001
            pass
    try:
        return derive_structure_context_capabilities(
            selected_chapter_orders=tuple(
                capabilities.get("selected_chapter_orders") or ()
            ),
            all_chapter_orders=tuple(capabilities.get("all_chapter_orders") or ()),
            selected_paragraph_count=int(
                capabilities.get("selected_paragraph_count")
                or capabilities.get("selected_chapter_count")
                or 0
            ),
            batch_index=int(capabilities.get("batch_index") or 0),
            batch_count=int(capabilities.get("batch_count") or 1),
            full_book_default=bool(
                capabilities.get("is_full_book_coverage")
                or capabilities.get("full_book_coverage")
                or False
            ),
            has_beginning_window=capabilities.get("has_beginning_window"),
            has_middle_window=capabilities.get("has_middle_window"),
            has_ending_window=capabilities.get("has_ending_window"),
        )
    except Exception:  # noqa: BLE001
        return None


def _try_private_validate(
    structured: Mapping[str, Any],
    *,
    catalog: Any,
    capabilities: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from storylens_private_engine.citation import validate_structure_stages_result_v2
        from storylens_private_engine.citation.structure_field_policy import (
            StructureContextCapabilities,
            derive_structure_context_capabilities,
        )
    except Exception:  # noqa: BLE001
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    private_catalog = _catalog_for_private_engine(catalog)
    if private_catalog is None:
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    caps_obj = None
    if capabilities:
        try:
            if isinstance(capabilities, StructureContextCapabilities):
                caps_obj = capabilities
            else:
                caps_obj = derive_structure_context_capabilities(
                    selected_chapter_orders=tuple(
                        capabilities.get("selected_chapter_orders") or ()
                    ),
                    all_chapter_orders=tuple(
                        capabilities.get("all_chapter_orders") or ()
                    ),
                    selected_paragraph_count=int(
                        capabilities.get("selected_paragraph_count")
                        or capabilities.get("selected_chapter_count")
                        or 0
                    ),
                    batch_index=int(capabilities.get("batch_index") or 0),
                    batch_count=int(capabilities.get("batch_count") or 1),
                    full_book_default=bool(
                        capabilities.get("is_full_book_coverage")
                        or capabilities.get("full_book_coverage")
                        or False
                    ),
                    has_beginning_window=capabilities.get("has_beginning_window"),
                    has_middle_window=capabilities.get("has_middle_window"),
                    has_ending_window=capabilities.get("has_ending_window"),
                )
        except Exception:  # noqa: BLE001
            caps_obj = None
    try:
        dto, err = validate_structure_stages_result_v2(
            structured, private_catalog, capabilities=caps_obj
        )
    except TypeError:
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    except Exception:  # noqa: BLE001
        return None, "PRIVATE_CITATION_VALIDATOR_UNAVAILABLE"
    if dto is None:
        return None, str(err or FAILURE_DTO_VALIDATION)
    if hasattr(dto, "model_dump"):
        return dict(dto.model_dump(mode="json")), None
    return dict(structured), None


def _public_shape_validate(
    structured: Mapping[str, Any],
    *,
    allowed_citation_ids: Sequence[str],
    capabilities: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fallback shape/membership check when private validator is unavailable."""

    from app.narrative_core.product_contract.module_results import (
        CitedBoundaryDto,
        CitedClaimDto,
        CoverageScope,
        StructureStageV2,
        StructureStagesResultV2,
        TurningPointV2,
    )

    allowed = {str(x) for x in allowed_citation_ids}
    try:
        if str(structured.get("contract_version") or "") != "v2":
            return None, FAILURE_DTO_VALIDATION
        coverage_scope = str(structured.get("coverage_scope") or "").strip()
        raw_stages = list(structured.get("stages") or ())
        raw_tps = list(structured.get("turning_points") or ())
        if not isinstance(structured.get("stages"), (list, tuple)):
            return None, FAILURE_DTO_VALIDATION
        if not isinstance(structured.get("turning_points"), (list, tuple)):
            return None, FAILURE_DTO_VALIDATION

        # Prefer private coverage-scope capability check when present.
        try:
            from storylens_private_engine.citation.structure_field_policy import (
                derive_structure_context_capabilities,
                validate_coverage_scope_against_capabilities,
            )

            caps = derive_structure_context_capabilities(
                selected_chapter_orders=tuple(
                    (capabilities or {}).get("selected_chapter_orders") or ()
                ),
                all_chapter_orders=tuple(
                    (capabilities or {}).get("all_chapter_orders") or ()
                ),
                selected_paragraph_count=int(
                    (capabilities or {}).get("selected_paragraph_count") or 0
                ),
                batch_index=int((capabilities or {}).get("batch_index") or 0),
                batch_count=int((capabilities or {}).get("batch_count") or 1),
                full_book_default=bool(
                    (capabilities or {}).get("is_full_book_coverage")
                    or (capabilities or {}).get("full_book_coverage")
                    or False
                ),
            )
            scope_err = validate_coverage_scope_against_capabilities(
                coverage_scope,
                caps,
                stage_count=len(raw_stages),
                limitations=tuple(structured.get("limitations") or ()),
            )
            if scope_err:
                return None, str(scope_err)
        except Exception:  # noqa: BLE001
            if coverage_scope not in {
                CoverageScope.LOCAL,
                CoverageScope.PARTIAL_SPAN,
                CoverageScope.FULL_SELECTED_RANGE,
                CoverageScope.INSUFFICIENT,
            }:
                return None, FAILURE_COVERAGE_SCOPE_INVALID
            if coverage_scope == CoverageScope.INSUFFICIENT and raw_stages:
                return None, FAILURE_COVERAGE_SCOPE_INVALID
            if coverage_scope != CoverageScope.INSUFFICIENT and not raw_stages:
                return None, FAILURE_COVERAGE_SCOPE_INVALID

        range_err = _validate_stage_ranges(
            [s for s in raw_stages if isinstance(s, Mapping)]
        )
        if range_err:
            return None, range_err

        seen_stage_keys: set[str] = set()
        seen_local_refs: set[str] = set()
        stages: list[StructureStageV2] = []
        for idx, raw in enumerate(raw_stages):
            if not isinstance(raw, Mapping):
                return None, FAILURE_DTO_VALIDATION
            stage_key = str(raw.get("stage_key") or "").strip() or f"STAGE-{idx + 1:03d}"
            local_ref = (
                str(raw.get("local_ref") or "").strip() or None
            )
            if stage_key in seen_stage_keys:
                return None, FAILURE_LOCAL_REF_DUPLICATE
            seen_stage_keys.add(stage_key)
            if local_ref:
                if local_ref in seen_local_refs:
                    return None, FAILURE_LOCAL_REF_DUPLICATE
                seen_local_refs.add(local_ref)

            summary_raw = raw.get("summary")
            if not isinstance(summary_raw, Mapping):
                return None, FAILURE_DTO_VALIDATION
            summary = CitedClaimDto(
                value=summary_raw.get("value"),
                status=str(summary_raw.get("status") or ""),
                citation_ids=tuple(str(x) for x in (summary_raw.get("citation_ids") or ())),
                confidence=summary_raw.get("confidence"),
            )
            if summary.status in {"observed", "inferred"} and not summary.citation_ids:
                return None, FAILURE_STAGE_SUMMARY_CITATION_EMPTY
            for cid in summary.citation_ids:
                err = _citation_allowed(cid, allowed)
                if err:
                    return None, err

            boundary_obj = raw.get("boundary")
            boundary_map = boundary_obj if isinstance(boundary_obj, Mapping) else {}
            start_raw = raw.get("start_boundary") or boundary_map.get("start")
            end_raw = raw.get("end_boundary") or boundary_map.get("end")
            if not isinstance(start_raw, Mapping):
                return None, FAILURE_STAGE_START_BOUNDARY_MISSING
            if not isinstance(end_raw, Mapping):
                return None, FAILURE_STAGE_END_BOUNDARY_MISSING
            start_ids = tuple(str(x) for x in (start_raw.get("citation_ids") or ()))
            end_ids = tuple(str(x) for x in (end_raw.get("citation_ids") or ()))
            if not start_ids:
                return None, FAILURE_STAGE_START_BOUNDARY_MISSING
            if not end_ids:
                return None, FAILURE_STAGE_END_BOUNDARY_MISSING
            for cid in (*start_ids, *end_ids):
                err = _citation_allowed(cid, allowed)
                if err:
                    return None, err
            start_boundary = CitedBoundaryDto(
                citation_ids=start_ids,
                value=start_raw.get("value"),
                status=start_raw.get("status"),
                confidence=start_raw.get("confidence"),
            )
            end_boundary = CitedBoundaryDto(
                citation_ids=end_ids,
                value=end_raw.get("value"),
                status=end_raw.get("status"),
                confidence=end_raw.get("confidence"),
            )
            stages.append(
                StructureStageV2(
                    stage_key=stage_key,
                    label=str(raw.get("label") or stage_key),
                    summary=summary,
                    start_boundary=start_boundary,
                    end_boundary=end_boundary,
                    chapter_range=_parse_chapter_range(raw.get("chapter_range")),
                    related_turning_point_keys=tuple(
                        str(x) for x in (raw.get("related_turning_point_keys") or ())
                    ),
                    order=int(raw.get("order") if raw.get("order") is not None else idx),
                    narrative_function=str(raw.get("narrative_function") or ""),
                    local_ref=local_ref,
                )
            )

        tps: list[TurningPointV2] = []
        seen_tp_keys: set[str] = set()
        for idx, raw in enumerate(raw_tps):
            if not isinstance(raw, Mapping):
                return None, FAILURE_DTO_VALIDATION
            tp_key = (
                str(raw.get("turning_point_key") or "").strip() or f"TP-{idx + 1:03d}"
            )
            local_ref = str(raw.get("local_ref") or "").strip() or None
            if tp_key in seen_tp_keys:
                return None, FAILURE_LOCAL_REF_DUPLICATE
            seen_tp_keys.add(tp_key)
            if local_ref:
                if local_ref in seen_local_refs:
                    return None, FAILURE_LOCAL_REF_DUPLICATE
                seen_local_refs.add(local_ref)
            desc_raw = raw.get("description") or raw.get("summary")
            if not isinstance(desc_raw, Mapping):
                return None, FAILURE_DTO_VALIDATION
            description = CitedClaimDto(
                value=desc_raw.get("value"),
                status=str(desc_raw.get("status") or ""),
                citation_ids=tuple(str(x) for x in (desc_raw.get("citation_ids") or ())),
                confidence=desc_raw.get("confidence"),
            )
            # Top-level citation_ids on TP (policy field) may supplement description.
            extra_ids = tuple(str(x) for x in (raw.get("citation_ids") or ()))
            if description.status in {"observed", "inferred"}:
                if not description.citation_ids and not extra_ids:
                    return None, FAILURE_TP_CITATION_EMPTY
            for cid in (*description.citation_ids, *extra_ids):
                err = _citation_allowed(cid, allowed)
                if err:
                    return None, err
            # Prefer claim citations; fold extras when claim empty.
            if not description.citation_ids and extra_ids:
                description = CitedClaimDto(
                    value=description.value,
                    status=description.status,
                    citation_ids=extra_ids,
                    confidence=description.confidence,
                )
            related = raw.get("related_stage_key")
            if related is not None and str(related) and str(related) not in seen_stage_keys:
                # Soft: unknown related stage key fails closed only when stages present.
                if stages:
                    return None, FAILURE_LOCAL_REF_UNKNOWN
            chapter_id = raw.get("chapter_id")
            tps.append(
                TurningPointV2(
                    turning_point_key=tp_key,
                    label=str(raw.get("label") or tp_key),
                    description=description,
                    chapter_id=None if chapter_id in (None, "") else int(chapter_id),
                    related_stage_key=str(related) if related else None,
                    local_ref=local_ref,
                )
            )

        dto = StructureStagesResultV2(
            stages=tuple(stages),
            turning_points=tuple(tps),
            coverage_scope=coverage_scope,
            contract_version="v2",
            overall_confidence=structured.get("overall_confidence"),
            limitations=tuple(str(x) for x in (structured.get("limitations") or ())),
        )
        return {
            "contract_version": dto.contract_version,
            "coverage_scope": dto.coverage_scope,
            "overall_confidence": dto.overall_confidence,
            "limitations": list(dto.limitations),
            "stages": [
                {
                    "stage_key": s.stage_key,
                    "label": s.label,
                    "summary": _claim_dict(s.summary),
                    "start_boundary": _boundary_dict(s.start_boundary),
                    "end_boundary": _boundary_dict(s.end_boundary),
                    "chapter_range": list(s.chapter_range),
                    "related_turning_point_keys": list(s.related_turning_point_keys),
                    "order": s.order,
                    "narrative_function": s.narrative_function,
                    **({"local_ref": s.local_ref} if s.local_ref else {}),
                }
                for s in dto.stages
            ],
            "turning_points": [
                {
                    "turning_point_key": t.turning_point_key,
                    "label": t.label,
                    "description": _claim_dict(t.description),
                    "chapter_id": t.chapter_id,
                    "related_stage_key": t.related_stage_key,
                    **({"local_ref": t.local_ref} if t.local_ref else {}),
                }
                for t in dto.turning_points
            ],
        }, None
    except Exception:  # noqa: BLE001
        return None, FAILURE_DTO_VALIDATION


def validate_structure_stages_provider_output_v2(
    structured: Any,
    *,
    catalog: Any | None = None,
    allowed_citation_ids: Sequence[str] | None = None,
    capabilities: Mapping[str, Any] | None = None,
) -> StructureStagesV2ContractValidation:
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
        return StructureStagesV2ContractValidation(
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
        sorted(k for k in observed if k not in STRUCTURE_STAGES_V2_ALLOWED_TOP_LEVEL)
    )
    diag["observed_top_level_fields"] = list(observed)
    diag["undeclared_top_level_fields"] = list(undeclared)
    if undeclared:
        return StructureStagesV2ContractValidation(
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

    required = ("contract_version", "coverage_scope", "stages", "turning_points")
    missing = tuple(name for name in required if name not in structured)
    if missing:
        return StructureStagesV2ContractValidation(
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
        typed, err = _public_shape_validate(
            structured,
            allowed_citation_ids=allowed,
            capabilities=capabilities,
        )

    if typed is None:
        return StructureStagesV2ContractValidation(
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

    return StructureStagesV2ContractValidation(
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
            "dto_runtime_type": "StructureStagesResultV2",
        },
    )


def structure_stages_result_v2_json_schema(
    *,
    citation_ids: Sequence[str] | None = None,
    catalog: Any | None = None,
) -> dict[str, Any]:
    """JSON Schema for Live binding. Prefer private dynamic schema when available."""

    if catalog is not None:
        try:
            from storylens_private_engine.citation import (
                structure_stages_result_v2_json_schema as _priv,
            )

            return dict(_priv(_catalog_for_private_engine(catalog)))
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
    boundary = {
        "type": "object",
        "properties": {
            "citation_ids": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", **({"enum": ids} if ids else {})},
            },
            "value": {"type": ["string", "null"]},
            "status": {
                "type": ["string", "null"],
                "enum": ["observed", "inferred", "not_observed", None],
            },
            "confidence": {"type": ["number", "null"]},
        },
        "required": ["citation_ids"],
        "additionalProperties": False,
    }
    stage = {
        "type": "object",
        "properties": {
            "stage_key": {"type": "string"},
            "local_ref": {"type": ["string", "null"]},
            "label": {"type": "string"},
            "summary": claim,
            "start_boundary": boundary,
            "end_boundary": boundary,
            "chapter_range": {
                "type": "array",
                "items": {"type": ["integer", "null"]},
                "minItems": 2,
                "maxItems": 2,
            },
            "related_turning_point_keys": {
                "type": "array",
                "items": {"type": "string"},
            },
            "order": {"type": "integer"},
            "narrative_function": {"type": "string"},
        },
        "required": [
            "stage_key",
            "label",
            "summary",
            "start_boundary",
            "end_boundary",
        ],
        "additionalProperties": False,
    }
    turning_point = {
        "type": "object",
        "properties": {
            "turning_point_key": {"type": "string"},
            "local_ref": {"type": ["string", "null"]},
            "label": {"type": "string"},
            "description": claim,
            "citation_ids": {
                "type": "array",
                "items": {"type": "string", **({"enum": ids} if ids else {})},
            },
            "chapter_id": {"type": ["integer", "null"]},
            "related_stage_key": {"type": ["string", "null"]},
        },
        "required": ["turning_point_key", "label", "description"],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": SCHEMA_ID,
        "type": "object",
        "properties": {
            "contract_version": {"type": "string", "const": "v2"},
            "coverage_scope": {
                "type": "string",
                "enum": [
                    "local",
                    "partial_span",
                    "full_selected_range",
                    "insufficient",
                ],
            },
            "stages": {"type": "array", "items": stage},
            "turning_points": {"type": "array", "items": turning_point},
            "overall_confidence": {"type": ["number", "null"]},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "contract_version",
            "coverage_scope",
            "stages",
            "turning_points",
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
