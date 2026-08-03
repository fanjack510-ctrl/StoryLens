"""ChapterFunctionsResultV2 → chapter_function asset candidates (WB-2.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.narrative_core.product_contract.module_results import (
    normalize_coverage_scope_wire,
)
from app.narrative_core.services.chapter_functions_output_contract_v2 import (
    OUTPUT_CONTRACT_ID,
    SCHEMA_ID,
    normalize_function_labels,
)

RESULT_SCHEMA_V2 = "ChapterFunctionsResultV2"
MAPPER_KEY_V2 = "chapter_functions:ChapterFunctionsResultV2"
EVIDENCE_CONTRACT_VERSION = "v2"


def chapter_function_output_ref(chapter_id: str | int) -> str:
    return f"chapter_functions.chapter.{chapter_id}"


def formal_chapter_functions_output_refs(
    *,
    chapters: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    refs: list[str] = ["chapter_functions.out"]
    for chapter in chapters:
        cid = chapter.get("chapter_id")
        if cid is None or str(cid).strip() == "":
            continue
        refs.append(chapter_function_output_ref(cid))
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ChapterFunctionsMappingResult:
    status: str
    failure_code: str | None
    mapper_key: str
    source_schema: str
    normalized: Mapping[str, Any]
    asset_candidates: tuple[Mapping[str, Any], ...]
    evidence_refs: tuple[Mapping[str, Any], ...]
    resolver_output_refs: tuple[str, ...]
    semantic_claim_count: int
    coverage_scope: str | None = None


def _evidence_item(
    *,
    citation_id: str,
    provider_ref: str,
    claim_key: str,
) -> dict[str, Any]:
    return {
        "evidence_id": citation_id,
        "evidence_key": citation_id,
        "candidate_id": citation_id,
        "citation_id": citation_id,
        "evidence_role": "support",
        "provider_output_ref": provider_ref,
        "target_output_ref": provider_ref,
        "claim_key": claim_key,
        "contract_version": EVIDENCE_CONTRACT_VERSION,
    }


def map_chapter_functions_result_v2(
    structured: Mapping[str, Any],
    *,
    catalog: Any | None = None,
    capabilities: Any | None = None,
) -> ChapterFunctionsMappingResult:
    """Map validated V2 payload → chapter_function assets + citation evidence refs."""

    _ = catalog
    _ = capabilities
    payload = {
        k: v
        for k, v in dict(structured).items()
        if k
        in {
            "contract_version",
            "evidence_contract_version",
            "coverage_scope",
            "chapters",
            "overall_confidence",
            "analysis_confidence",
            "limitations",
            "empty_reason",
            "context_capabilities",
        }
    }
    chapters = [c for c in (payload.get("chapters") or ()) if isinstance(c, Mapping)]
    evidence_bucket: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    claim_count = 0

    for index, chapter in enumerate(chapters):
        chapter_id = chapter.get("chapter_id")
        if chapter_id is None:
            continue
        out_ref = chapter_function_output_ref(chapter_id)
        primary, secondary, _err = normalize_function_labels(
            chapter.get("primary_function"),
            list(chapter.get("secondary_functions") or ()),
        )
        summary = (
            chapter.get("observed_summary")
            if isinstance(chapter.get("observed_summary"), Mapping)
            else {}
        )
        summary_text = str(summary.get("value") or "")
        labels = [x for x in ((primary,) if primary else ()) + tuple(secondary) if x]
        chapter_evidence: list[dict[str, Any]] = []
        support_ids = [str(x) for x in (chapter.get("supporting_citation_ids") or ())]
        for cid in list(summary.get("citation_ids") or ()) + support_ids:
            scid = str(cid)
            if not scid:
                continue
            ev = _evidence_item(
                citation_id=scid,
                provider_ref=out_ref,
                claim_key=out_ref,
            )
            chapter_evidence.append(ev)
            evidence_bucket.append(ev)
            claim_count += 1
        try:
            chapter_order = int(chapter.get("chapter_order") or index)
        except (TypeError, ValueError):
            chapter_order = index
        assets.append(
            {
                "asset_type": "chapter_function",
                "title": f"chapter-{chapter_id}-{primary or 'null'}"[:120],
                "summary": summary_text[:500],
                "output_ref": out_ref,
                "canonical_output_ref": out_ref,
                "claim_key": out_ref,
                "candidate_key": f"candidate:{out_ref}",
                "source_schema": RESULT_SCHEMA_V2,
                "source_field": "chapters",
                "source_index": index,
                "chapter_id": chapter_id,
                "chapter_order": chapter_order,
                "primary_function": primary,
                "secondary_functions": list(secondary),
                "function_labels": labels,
                "chapter_range": [chapter_order, chapter_order],
                "coverage_scope": payload.get("coverage_scope"),
                "claim_status": summary.get("status"),
                "citation_ids": list(summary.get("citation_ids") or ()) or support_ids,
                "contract_version": EVIDENCE_CONTRACT_VERSION,
                "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
                "provider_output_ref": out_ref,
                "review_status": "candidate",
                "is_canonical": False,
                "confidence": chapter.get("confidence"),
                "narrative_function": primary or (labels[0] if labels else ""),
                "provider_provenance": {
                    "schema": SCHEMA_ID,
                    "output_contract_id": OUTPUT_CONTRACT_ID,
                    "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
                },
            }
        )

    refs = formal_chapter_functions_output_refs(chapters=chapters)
    if not assets and str(payload.get("coverage_scope") or "") != "insufficient":
        return ChapterFunctionsMappingResult(
            status="rejected",
            failure_code="CANDIDATE_BUILD_REJECTED",
            mapper_key=MAPPER_KEY_V2,
            source_schema=RESULT_SCHEMA_V2,
            normalized=payload,
            asset_candidates=(),
            evidence_refs=(),
            resolver_output_refs=refs,
            semantic_claim_count=0,
            coverage_scope=normalize_coverage_scope_wire(payload.get("coverage_scope")),
        )

    return ChapterFunctionsMappingResult(
        status="mapped",
        failure_code=None,
        mapper_key=MAPPER_KEY_V2,
        source_schema=RESULT_SCHEMA_V2,
        normalized=payload,
        asset_candidates=tuple(assets),
        evidence_refs=tuple(evidence_bucket),
        resolver_output_refs=refs,
        semantic_claim_count=claim_count,
        coverage_scope=normalize_coverage_scope_wire(payload.get("coverage_scope")),
    )


def mapping_diagnostics(mapped: ChapterFunctionsMappingResult) -> dict[str, Any]:
    return {
        "mapper_key": mapped.mapper_key,
        "mapper_status": mapped.status,
        "dto_mapper_key": mapped.mapper_key,
        "dto_mapper_status": mapped.status,
        "dto_mapper_failure_code": mapped.failure_code,
        "failure_code": mapped.failure_code,
        "source_schema": mapped.source_schema,
        "semantic_claim_count": mapped.semantic_claim_count,
        "contract_version": EVIDENCE_CONTRACT_VERSION,
        "output_contract_id": OUTPUT_CONTRACT_ID,
        "coverage_scope": mapped.coverage_scope,
        "resolver_output_refs": list(mapped.resolver_output_refs),
    }


def lab_v1_items_from_chapter_functions_v2(
    structure_v2: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Adapter: V2 chapters → Lab ChapterFunctionsResultDto-shaped items."""

    items: list[dict[str, Any]] = []
    for chapter in structure_v2.get("chapters") or ():
        if not isinstance(chapter, Mapping):
            continue
        primary, secondary, _ = normalize_function_labels(
            chapter.get("primary_function"),
            list(chapter.get("secondary_functions") or ()),
        )
        labels = [x for x in ((primary,) if primary else ()) + tuple(secondary) if x]
        summary = (
            chapter.get("observed_summary")
            if isinstance(chapter.get("observed_summary"), Mapping)
            else {}
        )
        try:
            chapter_id = int(chapter.get("chapter_id"))
        except (TypeError, ValueError):
            chapter_id = 0
        try:
            chapter_order = int(chapter.get("chapter_order") or 0)
        except (TypeError, ValueError):
            chapter_order = 0
        items.append(
            {
                "chapter_id": chapter_id,
                "chapter_order": chapter_order,
                "function_labels": labels,
                "primary_storyline_ids": [],
                "character_focus_ids": [],
                "hook_ids": [],
                "payoff_ids": [],
                "change_summary": str(summary.get("value") or ""),
                "evidence_refs": [
                    {"evidence_id": cid, "evidence_role": "support"}
                    for cid in (chapter.get("supporting_citation_ids") or [])
                ],
                "primary_function": primary,
                "secondary_functions": list(secondary),
                "contract_version": "v1",
                "adapted_from": "ChapterFunctionsResultV2",
            }
        )
    return items
