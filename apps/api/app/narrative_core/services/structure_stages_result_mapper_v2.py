"""StructureStagesResultV2 → Candidates / Evidence (Public fallback mapper).

Prefer private StructureStagesResultMapperV2 when registered; this module keeps
the Public product path runnable while private symbols land.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.narrative_core.product_contract.module_results import (
    normalize_coverage_scope_wire,
)
from app.narrative_core.services.structure_stages_output_contract_v2 import (
    OUTPUT_CONTRACT_ID,
    SCHEMA_ID,
)

RESULT_SCHEMA_V2 = "StructureStagesResultV2"
MAPPER_KEY_V2 = "structure_stages:StructureStagesResultV2"
EVIDENCE_CONTRACT_VERSION = "v2"


def structure_stage_output_ref(stage_key: str) -> str:
    return f"structure_stages.stage.{stage_key}"


def structure_stage_boundary_start_ref(stage_key: str) -> str:
    return f"structure_stages.stage.{stage_key}.boundary.start"


def structure_stage_boundary_end_ref(stage_key: str) -> str:
    return f"structure_stages.stage.{stage_key}.boundary.end"


def structure_turning_point_output_ref(turning_point_key: str) -> str:
    return f"structure_stages.turning_point.{turning_point_key}"


def formal_structure_stages_output_refs(
    *,
    stages: Sequence[Mapping[str, Any]],
    turning_points: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Register formal output refs for Structure Stages V2."""

    refs: list[str] = ["structure_stages.out"]
    for stage in stages:
        key = str(stage.get("stage_key") or "").strip()
        if not key:
            continue
        refs.append(structure_stage_output_ref(key))
        refs.append(structure_stage_boundary_start_ref(key))
        refs.append(structure_stage_boundary_end_ref(key))
    for tp in turning_points:
        key = str(tp.get("turning_point_key") or "").strip()
        if key:
            refs.append(structure_turning_point_output_ref(key))
    # Stable unique order
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class StructureStagesMappingResult:
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


def map_structure_stages_result_v2(
    structured: Mapping[str, Any],
    *,
    catalog: Any | None = None,
    capabilities: Any | None = None,
) -> StructureStagesMappingResult:
    """Map validated V2 payload → STRUCTURE_STAGE assets + citation evidence refs.

    Turning points are NOT independent assets — they remain in normalized payload
    for Artifact / Result API projection.
    """

    # Prefer private mapper when available.
    try:
        from storylens_private_engine.modules.structure_stages.result_mapper_v2 import (
            get_structure_stages_result_mapper_v2,
        )
        from app.narrative_core.services.citation_catalog_v2 import (
            catalog_for_private_engine,
        )
        from app.narrative_core.services.structure_stages_output_contract_v2 import (
            resolve_structure_context_capabilities,
        )

        mapper = get_structure_stages_result_mapper_v2(
            catalog=catalog_for_private_engine(catalog),
            capabilities=resolve_structure_context_capabilities(capabilities),
        )
        mapped = mapper.map(structured)
        # Adapt private mapping result shape when present.
        assets = tuple(getattr(mapped, "asset_candidates", ()) or ())
        evidence = tuple(getattr(mapped, "evidence_refs", ()) or ())
        normalized = dict(getattr(mapped, "normalized", None) or structured)
        refs = formal_structure_stages_output_refs(
            stages=list(normalized.get("stages") or ()),
            turning_points=list(normalized.get("turning_points") or ()),
        )
        return StructureStagesMappingResult(
            status=str(getattr(mapped, "status", "mapped") or "mapped"),
            failure_code=getattr(mapped, "failure_code", None),
            mapper_key=str(getattr(mapped, "mapper_key", MAPPER_KEY_V2)),
            source_schema=str(getattr(mapped, "source_schema", RESULT_SCHEMA_V2)),
            normalized=normalized,
            asset_candidates=tuple(
                dict(a) if isinstance(a, Mapping) else {"value": a} for a in assets
            ),
            evidence_refs=tuple(
                dict(e) if isinstance(e, Mapping) else {"evidence_id": e} for e in evidence
            ),
            resolver_output_refs=refs,
            semantic_claim_count=int(
                getattr(mapped, "semantic_source_item_count", None)
                or getattr(mapped, "semantic_claim_count", None)
                or len(assets)
            ),
            coverage_scope=normalize_coverage_scope_wire(
                normalized.get("coverage_scope")
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    payload = {
        k: v
        for k, v in dict(structured).items()
        if k
        in {
            "contract_version",
            "coverage_scope",
            "stages",
            "turning_points",
            "overall_confidence",
            "limitations",
        }
    }
    stages = [s for s in (payload.get("stages") or ()) if isinstance(s, Mapping)]
    tps = [t for t in (payload.get("turning_points") or ()) if isinstance(t, Mapping)]
    evidence_bucket: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    claim_count = 0

    for index, stage in enumerate(stages):
        stage_key = str(stage.get("stage_key") or f"STAGE-{index + 1:03d}")
        stage_ref = structure_stage_output_ref(stage_key)
        start_ref = structure_stage_boundary_start_ref(stage_key)
        end_ref = structure_stage_boundary_end_ref(stage_key)
        summary = stage.get("summary") if isinstance(stage.get("summary"), Mapping) else {}
        start_b = (
            stage.get("start_boundary")
            if isinstance(stage.get("start_boundary"), Mapping)
            else {}
        )
        end_b = (
            stage.get("end_boundary") if isinstance(stage.get("end_boundary"), Mapping) else {}
        )
        summary_text = str(summary.get("value") or stage.get("label") or stage_key)
        stage_evidence: list[dict[str, Any]] = []
        for cid in summary.get("citation_ids") or ():
            ev = _evidence_item(
                citation_id=str(cid),
                provider_ref=stage_ref,
                claim_key=stage_ref,
            )
            stage_evidence.append(ev)
            evidence_bucket.append(ev)
            claim_count += 1
        for cid in start_b.get("citation_ids") or ():
            ev = _evidence_item(
                citation_id=str(cid),
                provider_ref=start_ref,
                claim_key=start_ref,
            )
            stage_evidence.append(ev)
            evidence_bucket.append(ev)
            claim_count += 1
        for cid in end_b.get("citation_ids") or ():
            ev = _evidence_item(
                citation_id=str(cid),
                provider_ref=end_ref,
                claim_key=end_ref,
            )
            stage_evidence.append(ev)
            evidence_bucket.append(ev)
            claim_count += 1

        chapter_range = stage.get("chapter_range")
        if isinstance(chapter_range, (list, tuple)) and len(chapter_range) == 2:
            cr = (chapter_range[0], chapter_range[1])
        else:
            cr = (None, None)
        related_tps = [
            str(x) for x in (stage.get("related_turning_point_keys") or ())
        ]
        assets.append(
            {
                "asset_type": "structure_stage",
                "title": str(stage.get("label") or stage_key)[:120],
                "summary": summary_text[:500],
                "output_ref": stage_ref,
                "canonical_output_ref": stage_ref,
                "claim_key": stage_ref,
                "candidate_key": f"candidate:{stage_ref}",
                "source_schema": RESULT_SCHEMA_V2,
                "source_field": "stages",
                "source_index": index,
                "stage_key": stage_key,
                "chapter_range": list(cr),
                "related_turning_point_keys": related_tps,
                "coverage_scope": payload.get("coverage_scope"),
                "claim_status": summary.get("status"),
                "citation_ids": list(summary.get("citation_ids") or ()),
                "boundary_start_citation_ids": list(start_b.get("citation_ids") or ()),
                "boundary_end_citation_ids": list(end_b.get("citation_ids") or ()),
                "contract_version": EVIDENCE_CONTRACT_VERSION,
                "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
                "provider_output_ref": stage_ref,
                "review_status": "candidate",
                "is_canonical": False,
                "confidence": summary.get("confidence"),
                "narrative_function": str(stage.get("narrative_function") or ""),
                "provider_provenance": {
                    "schema": SCHEMA_ID,
                    "output_contract_id": OUTPUT_CONTRACT_ID,
                    "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
                },
            }
        )

    # TP evidence binds to turning_point refs (no TP assets).
    for index, tp in enumerate(tps):
        tp_key = str(tp.get("turning_point_key") or f"TP-{index + 1:03d}")
        tp_ref = structure_turning_point_output_ref(tp_key)
        desc = tp.get("description") if isinstance(tp.get("description"), Mapping) else {}
        ids = list(desc.get("citation_ids") or ()) or list(tp.get("citation_ids") or ())
        for cid in ids:
            evidence_bucket.append(
                _evidence_item(
                    citation_id=str(cid),
                    provider_ref=tp_ref,
                    claim_key=tp_ref,
                )
            )
            claim_count += 1

    refs = formal_structure_stages_output_refs(stages=stages, turning_points=tps)
    if not assets and str(payload.get("coverage_scope") or "") != "insufficient":
        return StructureStagesMappingResult(
            status="rejected",
            failure_code="CANDIDATE_BUILD_REJECTED",
            mapper_key=MAPPER_KEY_V2,
            source_schema=RESULT_SCHEMA_V2,
            normalized=payload,
            asset_candidates=(),
            evidence_refs=(),
            resolver_output_refs=refs,
            semantic_claim_count=0,
            coverage_scope=normalize_coverage_scope_wire(
                payload.get("coverage_scope")
            ),
        )

    return StructureStagesMappingResult(
        status="mapped",
        failure_code=None,
        mapper_key=MAPPER_KEY_V2,
        source_schema=RESULT_SCHEMA_V2,
        normalized=payload,
        asset_candidates=tuple(assets),
        evidence_refs=tuple(evidence_bucket),
        resolver_output_refs=refs,
        semantic_claim_count=claim_count,
        coverage_scope=normalize_coverage_scope_wire(
            payload.get("coverage_scope")
        ),
    )


def mapping_diagnostics(mapped: StructureStagesMappingResult) -> dict[str, Any]:
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
