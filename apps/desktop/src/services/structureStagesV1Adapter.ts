/**
 * V1 StructureStagesResultDto → V2 adapter (Lab / historical only).
 * Free product write path must never use V1 as SoT.
 */
import type { StructureStagesResultDto } from "../features/wholeBook/contracts/moduleResults";
import {
  STRUCTURE_STAGES_EVIDENCE_CONTRACT_VERSION,
  STRUCTURE_STAGES_WIRE_CONTRACT_VERSION,
  type StructureStagesResultV2,
  type StructureStageV2,
  type TurningPointV2,
} from "./structureStagesResultV2";

const ADAPTER_PLACEHOLDER_CITATION = "CIT-ADAPTER-0001";

function claimFromText(value: string | null | undefined): StructureStageV2["summary"] {
  const text = (value ?? "").trim();
  if (!text) {
    return { value: null, status: "not_observed", citation_ids: [], confidence: null };
  }
  return {
    value: text,
    status: "inferred",
    citation_ids: [ADAPTER_PLACEHOLDER_CITATION],
    confidence: null,
  };
}

function boundaryFromChapter(
  chapter: number | null | undefined,
): StructureStageV2["start_boundary"] {
  return {
    citation_ids: [ADAPTER_PLACEHOLDER_CITATION],
    value: chapter == null ? null : `chapter:${chapter}`,
    note: "v1-adapter",
    status: "inferred",
    confidence: null,
  };
}

/**
 * Adapt Lab V1 DTO into a StructureStagesResultV2-shaped object for display-only.
 * Marks limitations so UI never confuses this with a native V2 product result.
 */
export function adaptStructureStagesV1ToV2(
  v1: StructureStagesResultDto,
): StructureStagesResultV2 {
  const stages: StructureStageV2[] = (v1.stages ?? []).map((stage, index) => {
    const start = stage.chapter_range?.[0] ?? null;
    const end = stage.chapter_range?.[1] ?? null;
    return {
      local_stage_ref: stage.stage_id || `S${index + 1}`,
      stage_key: stage.stage_id || null,
      title: stage.label || `阶段 ${index + 1}`,
      order_index: stage.order ?? index,
      stage_type: "unknown",
      summary: claimFromText(stage.narrative_function || stage.label),
      start_boundary: boundaryFromChapter(start),
      end_boundary: boundaryFromChapter(end),
      supporting_citation_ids: [],
      related_turning_point_refs: [],
      narrative_function: stage.narrative_function || null,
      confidence: v1.confidence ?? null,
      chapter_range: [start, end],
    };
  });

  const turning_points: TurningPointV2[] = (v1.turning_points ?? []).map((tp, index) => ({
    local_turning_point_ref: tp.turning_point_id || `TP${index + 1}`,
    turning_point_key: tp.turning_point_id || null,
    title: tp.label || `转折点 ${index + 1}`,
    order_index: index,
    turning_point_type: "unknown",
    description: claimFromText(tp.summary || tp.label),
    citation_ids: [ADAPTER_PLACEHOLDER_CITATION],
    related_stage_refs: [],
    confidence: v1.confidence ?? null,
    chapter_id: tp.chapter_id ?? null,
  }));

  const coverage_scope =
    stages.length === 0 ? "insufficient" : "partial_span";

  return {
    contract_version: STRUCTURE_STAGES_WIRE_CONTRACT_VERSION,
    evidence_contract_version: STRUCTURE_STAGES_EVIDENCE_CONTRACT_VERSION,
    coverage_scope,
    stages,
    turning_points,
    analysis_confidence: v1.confidence ?? null,
    overall_confidence: v1.confidence ?? null,
    limitations: [
      "V1_ADAPTER_ONLY",
      "LAB_COMPATIBILITY_PROJECTION",
      ...(v1.act_or_phase_labels?.length
        ? [`v1_labels:${v1.act_or_phase_labels.join("|")}`]
        : []),
    ],
    context_capabilities: {
      adapted_from: "StructureStagesResultDto",
      adapter: "structureStagesV1Adapter",
    },
  };
}
