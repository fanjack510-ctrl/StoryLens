"""BookOverview provider output contract (CHG-057).

Formal output is flat BookOverviewResultDto only.
Undeclared wrappers (book_overview / evidence_map / synthetic) are rejected —
never parsed as a new envelope contract.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any, Mapping, Sequence

from app.narrative_core.product_contract.module_results import (
    BookOverviewResultDto,
    EvidenceRefLite,
)

OUTPUT_CONTRACT_ID = "book_overview.BookOverviewResultDto"
OUTPUT_CONTRACT_VERSION = "1.0.0"
REPAIR_POLICY_ID = "book_overview.schema_repair"
REPAIR_POLICY_VERSION = "1.0.0"
MAX_REPAIR_COUNT = 1
SCHEMA_ID = "BookOverviewResultDto"
SCHEMA_REF = "dto://BookOverviewResultDto"

# Exact top-level keys allowed for flat BookOverviewResultDto.
BOOK_OVERVIEW_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    f.name for f in fields(BookOverviewResultDto)
)

# Explicitly undeclared / forbidden top-level keys observed in Live deviation.
BOOK_OVERVIEW_UNDECLARED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "book_overview",
        "evidence_map",
        "synthetic",
        "fake",
        "result",
        "data",
        "output",
        "module_output",
        "moduleOutput",
        "claims",
        "module_outputs",
        "parameters",
        "payload",
        "BookOverviewResult",
        "BookOverviewResultDto",
        "bookOverview",
        "bookOverviewResultDto",
        # Internal audit keys must not appear in provider content.
        "_provider_audit",
        "repaired",
    }
)

FAILURE_UNDECLARED_TOP_LEVEL = "UNDECLARED_TOP_LEVEL_FIELDS"
FAILURE_MISSING_REQUIRED = "MISSING_REQUIRED_FIELDS"
FAILURE_TYPE_ERROR = "DTO_TYPE_ERROR"
FAILURE_EMPTY_SEMANTIC = "EMPTY_SEMANTIC_FIELDS"
FAILURE_EMPTY_EVIDENCE_REFS = "EMPTY_EVIDENCE_REFS"
FAILURE_NOT_OBJECT = "STRUCTURED_OUTPUT_NOT_OBJECT"
FAILURE_DTO_VALIDATION = "DTO_VALIDATION_FAILED"
FAILURE_REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"
FAILURE_REPAIR_BUDGET = "REPAIR_BUDGET_EXCEEDED"


@dataclass(frozen=True, slots=True)
class BookOverviewContractValidation:
    ok: bool
    failure_code: str | None
    observed_top_level_fields: tuple[str, ...]
    undeclared_top_level_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    dto: BookOverviewResultDto | None
    typed_payload: dict[str, Any] | None
    schema_id: str | None
    schema_label_verified: bool
    diagnostics: Mapping[str, Any]


def book_overview_result_json_schema() -> dict[str, Any]:
    """Machine-readable JSON Schema derived from BookOverviewResultDto fields.

    Single source of truth: dataclass field names/types. No hand-written parallel schema.
    """

    evidence_item = {
        "type": "object",
        "properties": {
            "evidence_id": {"type": ["string", "integer"]},
            "evidence_role": {"type": "string"},
        },
        "required": ["evidence_id"],
        "additionalProperties": False,
    }
    properties: dict[str, Any] = {
        "logline": {"type": "string"},
        "premise": {"type": "string"},
        "central_question": {"type": "string"},
        "primary_conflict": {"type": "string"},
        "protagonist_asset_id": {"type": ["integer", "null"]},
        "major_storyline_ids": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "structure_summary": {"type": "string"},
        "ending_state": {"type": "string"},
        "evidence_refs": {
            "type": "array",
            "items": evidence_item,
            "minItems": 1,
        },
        "confidence": {"type": ["number", "null"]},
    }
    # Required = all dataclass fields except confidence (has default).
    required = [
        f.name
        for f in fields(BookOverviewResultDto)
        if f.name != "confidence"
    ]
    # Mechanical consistency check vs DTO field set.
    assert set(properties) == BOOK_OVERVIEW_ALLOWED_TOP_LEVEL
    assert set(required) | {"confidence"} == BOOK_OVERVIEW_ALLOWED_TOP_LEVEL
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": SCHEMA_ID,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
        "x_storylens_contract_id": OUTPUT_CONTRACT_ID,
        "x_storylens_contract_version": OUTPUT_CONTRACT_VERSION,
        "x_storylens_schema_ref": SCHEMA_REF,
    }


def book_overview_schema_fingerprint() -> str:
    raw = json.dumps(
        book_overview_result_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def provider_output_constraint_text() -> str:
    """Prompt output constraint generated from the formal schema identity."""

    fields_list = ", ".join(sorted(BOOK_OVERVIEW_ALLOWED_TOP_LEVEL))
    return (
        f"Output contract: {OUTPUT_CONTRACT_ID}@{OUTPUT_CONTRACT_VERSION} "
        f"({SCHEMA_REF}). "
        f"Return ONLY one flat JSON object with keys: {fields_list}. "
        "Do NOT wrap in book_overview. Do NOT include evidence_map. "
        "Do NOT include synthetic. Do NOT include claims[]. "
        "Do NOT return Markdown fences or explanatory prose. "
        "Put Evidence only in evidence_refs as "
        "{evidence_id, evidence_role}. "
        "evidence_id must be a Context Evidence Key visible in this request. "
        "protagonist_asset_id may be null; major_storyline_ids may be []. "
        "Do not invent database asset IDs."
    )


def repair_instruction_text(*, failure_code: str, observed_fields: Sequence[str]) -> str:
    observed = ",".join(str(x) for x in observed_fields[:32])
    return (
        f"SCHEMA REPAIR (max 1). Previous output failed formal contract "
        f"({failure_code}; observed_top_level=[{observed}]). "
        + provider_output_constraint_text()
        + " Regenerate the flat BookOverviewResultDto only."
    )


def _coerce_evidence_refs(raw: Any) -> tuple[EvidenceRefLite, ...]:
    if raw is None:
        return ()
    items = raw if isinstance(raw, (list, tuple)) else (raw,)
    out: list[EvidenceRefLite] = []
    for item in items:
        if isinstance(item, EvidenceRefLite):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            eid = item.get("evidence_id", item.get("evidenceId"))
            role = item.get("evidence_role", item.get("evidenceRole", "support"))
            if eid is None:
                raise ValueError("evidence_refs item missing evidence_id")
            out.append(EvidenceRefLite(evidence_id=eid, evidence_role=str(role or "support")))
            continue
        if isinstance(item, (str, int)):
            out.append(EvidenceRefLite(evidence_id=item, evidence_role="support"))
            continue
        raise ValueError("evidence_refs item type invalid")
    return tuple(out)


def _coerce_storyline_ids(raw: Any) -> tuple[int, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("major_storyline_ids must be array")
    out: list[int] = []
    for item in raw:
        out.append(int(item))
    return tuple(out)


def validate_book_overview_provider_output(
    structured: Any,
) -> BookOverviewContractValidation:
    """Exact top-level + DTO validation. Never unwraps wrappers. Never reads evidence_map."""

    diag: dict[str, Any] = {
        "output_contract_id": OUTPUT_CONTRACT_ID,
        "output_contract_version": OUTPUT_CONTRACT_VERSION,
        "dto_schema_id": None,
        "dto_validation_status": "PENDING",
        "schema_label_verified": False,
        "exact_contract_status": "PENDING",
    }
    if not isinstance(structured, Mapping):
        return BookOverviewContractValidation(
            ok=False,
            failure_code=FAILURE_NOT_OBJECT,
            observed_top_level_fields=(),
            undeclared_top_level_fields=(),
            missing_required_fields=(),
            dto=None,
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
        sorted(
            k
            for k in observed
            if k not in BOOK_OVERVIEW_ALLOWED_TOP_LEVEL
            or k in BOOK_OVERVIEW_UNDECLARED_TOP_LEVEL
        )
    )
    # Any key outside allowed set is undeclared.
    undeclared = tuple(
        sorted({*undeclared, *(k for k in observed if k not in BOOK_OVERVIEW_ALLOWED_TOP_LEVEL)})
    )
    diag["observed_top_level_fields"] = list(observed)
    diag["undeclared_top_level_fields"] = list(undeclared)

    if undeclared:
        return BookOverviewContractValidation(
            ok=False,
            failure_code=FAILURE_UNDECLARED_TOP_LEVEL,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=undeclared,
            missing_required_fields=(),
            dto=None,
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

    required = [f.name for f in fields(BookOverviewResultDto) if f.name != "confidence"]
    missing = tuple(name for name in required if name not in structured)
    if missing:
        return BookOverviewContractValidation(
            ok=False,
            failure_code=FAILURE_MISSING_REQUIRED,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=(),
            missing_required_fields=missing,
            dto=None,
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

    try:
        evidence_refs = _coerce_evidence_refs(structured.get("evidence_refs"))
        if not evidence_refs:
            return BookOverviewContractValidation(
                ok=False,
                failure_code=FAILURE_EMPTY_EVIDENCE_REFS,
                observed_top_level_fields=observed,
                undeclared_top_level_fields=(),
                missing_required_fields=(),
                dto=None,
                typed_payload=None,
                schema_id=None,
                schema_label_verified=False,
                diagnostics={
                    **diag,
                    "exact_contract_status": "FAILED",
                    "dto_validation_status": "FAILED",
                    "failure_code": FAILURE_EMPTY_EVIDENCE_REFS,
                },
            )
        protagonist = structured.get("protagonist_asset_id")
        if protagonist is not None:
            protagonist = int(protagonist)
        dto = BookOverviewResultDto(
            logline=str(structured.get("logline") or ""),
            premise=str(structured.get("premise") or ""),
            central_question=str(structured.get("central_question") or ""),
            primary_conflict=str(structured.get("primary_conflict") or ""),
            protagonist_asset_id=protagonist,
            major_storyline_ids=_coerce_storyline_ids(structured.get("major_storyline_ids")),
            structure_summary=str(structured.get("structure_summary") or ""),
            ending_state=str(structured.get("ending_state") or ""),
            evidence_refs=evidence_refs,
            confidence=(
                float(structured["confidence"])
                if structured.get("confidence") is not None
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        return BookOverviewContractValidation(
            ok=False,
            failure_code=FAILURE_TYPE_ERROR,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=(),
            missing_required_fields=(),
            dto=None,
            typed_payload=None,
            schema_id=None,
            schema_label_verified=False,
            diagnostics={
                **diag,
                "exact_contract_status": "FAILED",
                "dto_validation_status": "FAILED",
                "failure_code": FAILURE_TYPE_ERROR,
                "type_error_class": type(exc).__name__,
            },
        )

    semantic = (
        dto.logline,
        dto.premise,
        dto.central_question,
        dto.primary_conflict,
        dto.structure_summary,
        dto.ending_state,
    )
    if not any(str(x).strip() for x in semantic):
        return BookOverviewContractValidation(
            ok=False,
            failure_code=FAILURE_EMPTY_SEMANTIC,
            observed_top_level_fields=observed,
            undeclared_top_level_fields=(),
            missing_required_fields=(),
            dto=None,
            typed_payload=None,
            schema_id=None,
            schema_label_verified=False,
            diagnostics={
                **diag,
                "exact_contract_status": "FAILED",
                "dto_validation_status": "FAILED",
                "failure_code": FAILURE_EMPTY_SEMANTIC,
            },
        )

    typed = asdict(dto) if is_dataclass(dto) else dict(structured)
    # schema_id only after real DTO validation success
    return BookOverviewContractValidation(
        ok=True,
        failure_code=None,
        observed_top_level_fields=observed,
        undeclared_top_level_fields=(),
        missing_required_fields=(),
        dto=dto,
        typed_payload=typed,
        schema_id=SCHEMA_ID,
        schema_label_verified=True,
        diagnostics={
            **diag,
            "exact_contract_status": "SUCCESS",
            "dto_validation_status": "SUCCESS",
            "dto_schema_id": SCHEMA_ID,
            "dto_runtime_type": type(dto).__name__,
            "schema_label_verified": True,
            "provider_evidence_ref_count": len(dto.evidence_refs),
        },
    )


def strip_provider_audit(structured: Mapping[str, Any]) -> dict[str, Any]:
    """Remove adapter-injected audit keys before contract validation."""

    return {
        k: v
        for k, v in structured.items()
        if k not in {"_provider_audit", "repaired"}
    }


__all__ = [
    "OUTPUT_CONTRACT_ID",
    "OUTPUT_CONTRACT_VERSION",
    "REPAIR_POLICY_ID",
    "REPAIR_POLICY_VERSION",
    "MAX_REPAIR_COUNT",
    "SCHEMA_ID",
    "SCHEMA_REF",
    "BOOK_OVERVIEW_ALLOWED_TOP_LEVEL",
    "BOOK_OVERVIEW_UNDECLARED_TOP_LEVEL",
    "FAILURE_UNDECLARED_TOP_LEVEL",
    "FAILURE_MISSING_REQUIRED",
    "FAILURE_TYPE_ERROR",
    "FAILURE_EMPTY_SEMANTIC",
    "FAILURE_EMPTY_EVIDENCE_REFS",
    "FAILURE_NOT_OBJECT",
    "FAILURE_DTO_VALIDATION",
    "FAILURE_REPAIR_EXHAUSTED",
    "FAILURE_REPAIR_BUDGET",
    "BookOverviewContractValidation",
    "book_overview_result_json_schema",
    "book_overview_schema_fingerprint",
    "provider_output_constraint_text",
    "repair_instruction_text",
    "validate_book_overview_provider_output",
    "strip_provider_audit",
]
