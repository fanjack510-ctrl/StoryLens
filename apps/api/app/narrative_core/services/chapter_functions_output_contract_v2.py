"""ChapterFunctions Citation Evidence Contract V2 (WB-2.2 / CHG-20260802-040).

Formal Free product output is flat ChapterFunctionsResultV2 only.
Citation membership is validated against the request-bound CitationCatalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

OUTPUT_CONTRACT_ID = "ChapterFunctionsResultV2"
OUTPUT_CONTRACT_VERSION = "2.0.0"
REPAIR_POLICY_ID = "chapter_functions.schema_and_citation_repair"
REPAIR_POLICY_VERSION = "1.0.0"
MAX_REPAIR_COUNT = 1
SCHEMA_ID = "ChapterFunctionsResultV2"
SCHEMA_REF = "dto://ChapterFunctionsResultV2"

CHAPTER_FUNCTIONS_V2_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "contract_version",
        "evidence_contract_version",
        "coverage_scope",
        "context_capabilities",
        "chapters",
        "analysis_confidence",
        "overall_confidence",
        "limitations",
        "empty_reason",
        "provenance",
        "source_revision",
    }
)

FAILURE_NOT_OBJECT = "STRUCTURED_OUTPUT_NOT_OBJECT"
FAILURE_UNDECLARED_TOP_LEVEL = "UNDECLARED_TOP_LEVEL_FIELDS"
FAILURE_MISSING_REQUIRED = "MISSING_REQUIRED_FIELDS"
FAILURE_DTO_VALIDATION = "DTO_VALIDATION_FAILED"
FAILURE_UNKNOWN_CITATION = "UNKNOWN_CITATION_ID"
FAILURE_STALE_CITATION = "STALE_CITATION_ID"
FAILURE_COVERAGE_SCOPE_INVALID = "CHAPTER_FN_CONTRACT_FAILURE"
FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH = "CHAPTER_FN_COVERAGE_SCOPE_BINDING_MISMATCH"
FAILURE_REQUIRED_CHAPTER_MISSING = "CHAPTER_FN_REQUIRED_CHAPTER_MISSING"
FAILURE_EMPTY_RESULT_AFTER_REPAIR = "CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR"
FAILURE_CHAPTER_FN_CONTRACT = "CHAPTER_FN_CONTRACT_FAILURE"
FAILURE_LABEL_UNKNOWN = "CHAPTER_FN_LABEL_UNKNOWN"
FAILURE_PRIMARY_SECONDARY_CONFLICT = "CHAPTER_FN_PRIMARY_SECONDARY_CONFLICT"
FAILURE_CITATION_EMPTY = "CHAPTER_FN_CITATION_EMPTY"
FAILURE_CHAPTER_ORDER_DUPLICATE = "CHAPTER_FN_CHAPTER_ORDER_DUPLICATE"
FAILURE_CHAPTER_ID_DUPLICATE = "CHAPTER_FN_CONTRACT_FAILURE"
FAILURE_REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"

CANONICAL_FUNCTION_LABELS: frozenset[str] = frozenset(
    {
        "setup",
        "escalation",
        "climax",
        "resolution",
        "transition",
        "side_story",
        "flashback",
        "empty",
        "non_mainline",
        "unknown",
    }
)

_LABEL_SYNONYMS: dict[str, str] = {
    "rising": "escalation",
    "rising_action": "escalation",
    "ending": "resolution",
    "denouement": "resolution",
    "bridge": "transition",
    "aside": "side_story",
    "none": "empty",
    "blank": "empty",
}


def normalize_function_label(raw: Any) -> str | None:
    """Normalize one label via freeze synonym table; None if empty input."""

    if raw is None:
        return None
    text = str(raw).strip().lower().replace("-", "_")
    if not text:
        return None
    return _LABEL_SYNONYMS.get(text, text)


def normalize_function_labels(
    primary: Any,
    secondary: Sequence[Any] | None = None,
) -> tuple[str | None, tuple[str, ...], str | None]:
    """Normalize primary/secondary; return (primary, secondary, failure_code|None)."""

    primary_norm = normalize_function_label(primary)
    if primary is not None and str(primary).strip() and primary_norm is None:
        return None, (), FAILURE_LABEL_UNKNOWN
    if primary_norm is not None and primary_norm not in CANONICAL_FUNCTION_LABELS:
        return None, (), FAILURE_LABEL_UNKNOWN

    seen: list[str] = []
    for item in secondary or ():
        norm = normalize_function_label(item)
        if item is not None and str(item).strip() and norm is None:
            return primary_norm, (), FAILURE_LABEL_UNKNOWN
        if norm is None:
            continue
        if norm not in CANONICAL_FUNCTION_LABELS:
            return primary_norm, (), FAILURE_LABEL_UNKNOWN
        if primary_norm is not None and norm == primary_norm:
            continue
        if norm in seen:
            continue
        seen.append(norm)
    return primary_norm, tuple(seen), None


@dataclass(frozen=True, slots=True)
class ChapterFunctionsV2ContractValidation:
    ok: bool
    failure_code: str | None
    observed_top_level_fields: tuple[str, ...]
    undeclared_top_level_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    typed_payload: dict[str, Any] | None
    schema_id: str | None
    schema_label_verified: bool
    diagnostics: Mapping[str, Any]


def is_chapter_functions_v2_schema_bound(
    *,
    schema_ref: str | None = None,
    schema_title: Any = None,
) -> bool:
    ref = str(schema_ref or "")
    title = str(schema_title or "")
    return (
        "ChapterFunctionsResultV2" in ref
        or ref.endswith("dto://ChapterFunctionsResultV2")
        or title == "ChapterFunctionsResultV2"
        or "ChapterFunctionsResultV2" in title
    )


def provider_output_constraint_text_v2(
    *,
    citation_ids: Sequence[str] | None = None,
    policy_text: str | None = None,
) -> str:
    ids = list(citation_ids or ())
    enum_hint = ", ".join(ids) if ids else "(catalog citation_ids)"
    labels = ", ".join(sorted(CANONICAL_FUNCTION_LABELS))
    policy = policy_text or (
        "Each chapter item: controlled primary_function (or null) + secondary_functions[]; "
        "observed/inferred claims require ≥1 catalog citation_id. "
        "Do not invent chapters outside the batch. No primary duplicate in secondary."
    )
    return (
        f"Output contract: {OUTPUT_CONTRACT_ID}@{OUTPUT_CONTRACT_VERSION} "
        f"({SCHEMA_REF}, contract_version=v2). "
        "Return ONLY one flat ChapterFunctionsResultV2 JSON object with chapters[]. "
        f"Controlled labels: {labels}. {policy} "
        f"citation_ids must be chosen from the complete catalog ({len(ids)} ids): {enum_hint}. "
        "Do NOT wrap in chapter_functions. Do NOT include evidence_map. "
        "Do NOT return Markdown fences."
    )


def repair_instruction_text_v2(
    *,
    failure_code: str,
    observed_fields: Sequence[str],
    citation_ids: Sequence[str] | None = None,
) -> str:
    ids = list(citation_ids or ())
    enum_hint = ", ".join(ids) if ids else "(catalog citation_ids)"
    return (
        f"Previous output failed V2 contract validation ({failure_code}). "
        f"Observed top-level fields: {', '.join(observed_fields) or '(none)'}. "
        "Regenerate a complete ChapterFunctionsResultV2 JSON object only. "
        f"Use only these citation_ids ({len(ids)}): {enum_hint}. "
        "Normalize labels via controlled synonym table; drop primary from secondary; "
        "coverage_scope must equal server-frozen expected_coverage_scope."
    )


def _citation_allowed(cid: str, allowed: set[str]) -> str | None:
    if cid in allowed:
        return None
    prefix = cid.split("-")[1] if cid.count("-") >= 2 else ""
    allowed_prefixes = {a.split("-")[1] for a in allowed if a.count("-") >= 2}
    if prefix and prefix not in allowed_prefixes:
        return FAILURE_STALE_CITATION
    return FAILURE_UNKNOWN_CITATION


def _validate_claim(
    claim: Any,
    *,
    allowed: set[str],
    required: bool,
) -> str | None:
    if claim is None:
        return FAILURE_DTO_VALIDATION if required else None
    if not isinstance(claim, Mapping):
        return FAILURE_DTO_VALIDATION
    status = str(claim.get("status") or "").strip()
    value = claim.get("value")
    cids = [str(x) for x in (claim.get("citation_ids") or ()) if str(x).strip()]
    if status in {"observed", "inferred"}:
        if not (isinstance(value, str) and value.strip()):
            return FAILURE_DTO_VALIDATION
        if not cids:
            return FAILURE_CITATION_EMPTY
        for cid in cids:
            err = _citation_allowed(cid, allowed)
            if err:
                return err
    elif status == "not_observed":
        if cids:
            return FAILURE_DTO_VALIDATION
    else:
        return FAILURE_DTO_VALIDATION
    return None


def _public_shape_validate(
    structured: Mapping[str, Any],
    *,
    allowed_citation_ids: Sequence[str],
    capabilities: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fallback shape/membership check for ChapterFunctionsResultV2."""

    from app.narrative_core.product_contract.module_results import (
        ChapterFunctionChapterV2,
        ChapterFunctionsResultV2,
        CitedClaimDto,
        CoverageScope,
        normalize_coverage_scope_wire,
    )

    allowed = {str(x) for x in allowed_citation_ids}
    caps = dict(capabilities or {})
    try:
        if str(structured.get("contract_version") or "") != "v2":
            return None, FAILURE_DTO_VALIDATION
        coverage_scope = normalize_coverage_scope_wire(
            structured.get("coverage_scope")
        ) or ""
        raw_chapters = list(structured.get("chapters") or ())
        if not isinstance(structured.get("chapters"), (list, tuple)):
            return None, FAILURE_DTO_VALIDATION

        expected = str(caps.get("expected_coverage_scope") or "").strip()
        permits_empty = bool(caps.get("permits_empty_observation"))
        requires_obs = bool(caps.get("requires_chapter_observation", not permits_empty))
        if expected and coverage_scope and coverage_scope != expected:
            return None, FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH
        if coverage_scope not in {
            CoverageScope.LOCAL,
            CoverageScope.PARTIAL_SPAN,
            CoverageScope.FULL_SELECTED_RANGE,
            CoverageScope.INSUFFICIENT,
        }:
            return None, FAILURE_COVERAGE_SCOPE_INVALID
        if coverage_scope == CoverageScope.INSUFFICIENT:
            if raw_chapters:
                return None, FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH
            if not permits_empty and requires_obs:
                return None, FAILURE_REQUIRED_CHAPTER_MISSING
        elif not raw_chapters:
            return None, FAILURE_REQUIRED_CHAPTER_MISSING

        typed_chapters: list[ChapterFunctionChapterV2] = []
        seen_orders: set[int] = set()
        seen_ids: set[str] = set()
        for item in raw_chapters:
            if not isinstance(item, Mapping):
                return None, FAILURE_DTO_VALIDATION
            chapter_id = item.get("chapter_id")
            if chapter_id is None or str(chapter_id).strip() == "":
                return None, FAILURE_DTO_VALIDATION
            cid_key = str(chapter_id)
            if cid_key in seen_ids:
                return None, FAILURE_CHAPTER_ID_DUPLICATE
            seen_ids.add(cid_key)
            try:
                chapter_order = int(item.get("chapter_order"))
            except (TypeError, ValueError):
                return None, FAILURE_DTO_VALIDATION
            if chapter_order in seen_orders:
                return None, FAILURE_CHAPTER_ORDER_DUPLICATE
            seen_orders.add(chapter_order)

            primary, secondary, label_err = normalize_function_labels(
                item.get("primary_function"),
                list(item.get("secondary_functions") or ()),
            )
            if label_err:
                return None, label_err

            summary = item.get("observed_summary")
            effect = item.get("inferred_effect")
            has_labels = primary is not None or bool(secondary)
            if has_labels or coverage_scope != CoverageScope.INSUFFICIENT:
                if summary is None and has_labels:
                    return None, FAILURE_DTO_VALIDATION
            if summary is not None:
                err = _validate_claim(summary, allowed=allowed, required=True)
                if err:
                    return None, err
            if effect is not None:
                err = _validate_claim(effect, allowed=allowed, required=False)
                if err:
                    return None, err

            support = [str(x) for x in (item.get("supporting_citation_ids") or ()) if str(x).strip()]
            if summary and isinstance(summary, Mapping):
                for cid in summary.get("citation_ids") or ():
                    scid = str(cid)
                    if scid not in support:
                        support.append(scid)
            for cid in support:
                err = _citation_allowed(cid, allowed)
                if err:
                    return None, err
            if summary and isinstance(summary, Mapping):
                status = str(summary.get("status") or "")
                if status in {"observed", "inferred"} and not support:
                    return None, FAILURE_CITATION_EMPTY

            try:
                conf = float(item.get("confidence"))
            except (TypeError, ValueError):
                return None, FAILURE_DTO_VALIDATION

            observed = None
            if isinstance(summary, Mapping):
                observed = CitedClaimDto(
                    value=summary.get("value"),
                    status=str(summary.get("status") or "not_observed"),
                    citation_ids=tuple(str(x) for x in (summary.get("citation_ids") or ())),
                    confidence=summary.get("confidence"),
                )
            inferred = None
            if isinstance(effect, Mapping):
                inferred = CitedClaimDto(
                    value=effect.get("value"),
                    status=str(effect.get("status") or "not_observed"),
                    citation_ids=tuple(str(x) for x in (effect.get("citation_ids") or ())),
                    confidence=effect.get("confidence"),
                )

            typed_chapters.append(
                ChapterFunctionChapterV2(
                    chapter_id=chapter_id if isinstance(chapter_id, int) else str(chapter_id),
                    chapter_order=chapter_order,
                    primary_function=primary,
                    secondary_functions=secondary,
                    confidence=conf,
                    supporting_citation_ids=tuple(support),
                    observed_summary=observed,
                    inferred_effect=inferred,
                    limitations=tuple(str(x) for x in (item.get("limitations") or ())),
                )
            )

        dto = ChapterFunctionsResultV2(
            chapters=tuple(typed_chapters),
            coverage_scope=coverage_scope,
            contract_version="v2",
            evidence_contract_version=str(
                structured.get("evidence_contract_version") or "v2"
            ),
            analysis_confidence=structured.get("analysis_confidence"),
            overall_confidence=structured.get("overall_confidence"),
            limitations=tuple(str(x) for x in (structured.get("limitations") or ())),
            context_capabilities=(
                dict(structured["context_capabilities"])
                if isinstance(structured.get("context_capabilities"), dict)
                else None
            ),
            empty_reason=(
                str(structured.get("empty_reason"))
                if structured.get("empty_reason") is not None
                else None
            ),
        )
        wire = {
            "contract_version": dto.contract_version,
            "evidence_contract_version": dto.evidence_contract_version,
            "coverage_scope": dto.coverage_scope,
            "chapters": [
                {
                    "chapter_id": ch.chapter_id,
                    "chapter_order": ch.chapter_order,
                    "primary_function": ch.primary_function,
                    "secondary_functions": list(ch.secondary_functions),
                    "confidence": ch.confidence,
                    "supporting_citation_ids": list(ch.supporting_citation_ids),
                    "observed_summary": (
                        {
                            "value": ch.observed_summary.value,
                            "status": ch.observed_summary.status,
                            "citation_ids": list(ch.observed_summary.citation_ids),
                            "confidence": ch.observed_summary.confidence,
                        }
                        if ch.observed_summary is not None
                        else None
                    ),
                    "inferred_effect": (
                        {
                            "value": ch.inferred_effect.value,
                            "status": ch.inferred_effect.status,
                            "citation_ids": list(ch.inferred_effect.citation_ids),
                            "confidence": ch.inferred_effect.confidence,
                        }
                        if ch.inferred_effect is not None
                        else None
                    ),
                    "limitations": list(ch.limitations),
                }
                for ch in dto.chapters
            ],
            "analysis_confidence": dto.analysis_confidence,
            "overall_confidence": dto.overall_confidence,
            "limitations": list(dto.limitations),
            "context_capabilities": dto.context_capabilities,
            "empty_reason": dto.empty_reason,
        }
        return wire, None
    except ValueError as exc:
        msg = str(exc)
        if "insufficient" in msg and "non-empty" in msg:
            return None, FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH
        if "requires ≥1 chapter" in msg or "requires" in msg and "chapter" in msg:
            return None, FAILURE_REQUIRED_CHAPTER_MISSING
        if "label" in msg.lower():
            return None, FAILURE_LABEL_UNKNOWN
        return None, FAILURE_DTO_VALIDATION
    except Exception:  # noqa: BLE001
        return None, FAILURE_CHAPTER_FN_CONTRACT


def validate_chapter_functions_provider_output_v2(
    structured: Any,
    *,
    allowed_citation_ids: Sequence[str] | None = None,
    catalog: Any | None = None,
    capabilities: Mapping[str, Any] | None = None,
    repair_count: int = 0,
) -> ChapterFunctionsV2ContractValidation:
    observed: tuple[str, ...] = ()
    if not isinstance(structured, Mapping):
        return ChapterFunctionsV2ContractValidation(
            ok=False,
            failure_code=FAILURE_NOT_OBJECT,
            observed_top_level_fields=(),
            undeclared_top_level_fields=(),
            missing_required_fields=("chapters", "coverage_scope", "contract_version"),
            typed_payload=None,
            schema_id=SCHEMA_ID,
            schema_label_verified=True,
            diagnostics={"repair_count": repair_count},
        )
    observed = tuple(sorted(str(k) for k in structured.keys()))
    undeclared = tuple(
        k for k in observed if k not in CHAPTER_FUNCTIONS_V2_ALLOWED_TOP_LEVEL
    )
    if undeclared:
        return ChapterFunctionsV2ContractValidation(
            ok=False,
            failure_code=FAILURE_UNDECLARED_TOP_LEVEL,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=undeclared,
            missing_required_fields=(),
            typed_payload=None,
            schema_id=SCHEMA_ID,
            schema_label_verified=True,
            diagnostics={"repair_count": repair_count},
        )
    missing = tuple(
        name
        for name in ("contract_version", "coverage_scope", "chapters")
        if name not in structured
    )
    if missing:
        return ChapterFunctionsV2ContractValidation(
            ok=False,
            failure_code=FAILURE_MISSING_REQUIRED,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=(),
            missing_required_fields=missing,
            typed_payload=None,
            schema_id=SCHEMA_ID,
            schema_label_verified=True,
            diagnostics={"repair_count": repair_count},
        )

    citation_ids: list[str] = list(allowed_citation_ids or ())
    if not citation_ids and catalog is not None:
        citation_ids = list(getattr(catalog, "citation_ids", None) or ())

    typed, err = _public_shape_validate(
        structured,
        allowed_citation_ids=citation_ids,
        capabilities=capabilities,
    )
    if err is not None or typed is None:
        code = err or FAILURE_DTO_VALIDATION
        if (
            repair_count >= MAX_REPAIR_COUNT
            and code
            in {
                FAILURE_REQUIRED_CHAPTER_MISSING,
                FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH,
                FAILURE_EMPTY_RESULT_AFTER_REPAIR,
            }
        ):
            code = FAILURE_EMPTY_RESULT_AFTER_REPAIR
        return ChapterFunctionsV2ContractValidation(
            ok=False,
            failure_code=code,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=(),
            missing_required_fields=(),
            typed_payload=None,
            schema_id=SCHEMA_ID,
            schema_label_verified=True,
            diagnostics={"repair_count": repair_count, "failure_code": code},
        )
    return ChapterFunctionsV2ContractValidation(
        ok=True,
        failure_code=None,
        observed_top_level_fields=observed,
        undeclared_top_level_fields=(),
        missing_required_fields=(),
        typed_payload=typed,
        schema_id=SCHEMA_ID,
        schema_label_verified=True,
        diagnostics={"repair_count": repair_count},
    )


def chapter_functions_result_v2_json_schema(
    *,
    catalog: Any | None = None,
) -> dict[str, Any]:
    ids = list(getattr(catalog, "citation_ids", None) or ())
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": SCHEMA_ID,
        "type": "object",
        "additionalProperties": False,
        "required": ["contract_version", "coverage_scope", "chapters"],
        "properties": {
            "contract_version": {"const": "v2"},
            "evidence_contract_version": {"const": "v2"},
            "coverage_scope": {
                "type": "string",
                "enum": [
                    "local",
                    "partial_span",
                    "full_selected_range",
                    "insufficient",
                ],
            },
            "chapters": {"type": "array", "items": {"type": "object"}},
            "analysis_confidence": {"type": ["number", "null"]},
            "overall_confidence": {"type": ["number", "null"]},
            "limitations": {"type": "array", "items": {"type": "string"}},
            "context_capabilities": {"type": "object"},
            "empty_reason": {"type": ["string", "null"]},
            "provenance": {"type": "object"},
            "source_revision": {"type": "object"},
        },
        "x-catalog-citation-ids": ids,
        "x-controlled-labels": sorted(CANONICAL_FUNCTION_LABELS),
    }
