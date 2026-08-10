import type { V2ResultOrigin, WholeBookAnalysisV2, WholeBookProgressV2 } from "./contracts";

const obj = (x: unknown): x is Record<string, unknown> =>
  Boolean(x) && typeof x === "object" && !Array.isArray(x);

const SCAFFOLD_STAGE_SUMMARY = "围绕目标、阻力与选择形成完整阶段";
const SCAFFOLD_STAGE_TITLE = /^阶段\s*\d+$/;

function normalizeResultOrigin(raw: unknown): V2ResultOrigin {
  const allowed: V2ResultOrigin[] = [
    "real_provider",
    "deterministic_local_merge",
    "deterministic_test",
    "fixture",
    "mock",
    "legacy_migration",
    "unknown",
  ];
  if (typeof raw === "string" && (allowed as string[]).includes(raw)) {
    return raw as V2ResultOrigin;
  }
  return "unknown";
}

export function hasScaffoldHeuristic(data: WholeBookAnalysisV2): boolean {
  for (const stage of data.story.structure_stages) {
    if (SCAFFOLD_STAGE_TITLE.test(stage.title)) return true;
    if (stage.summary.includes(SCAFFOLD_STAGE_SUMMARY)) return true;
  }
  for (const s of data.suspense.lifecycles) {
    if (s.question.includes("悬念@")) return true;
  }
  return false;
}

export function isRealProviderV2Result(data: WholeBookAnalysisV2): boolean {
  const origin = data.analysis_metadata.result_origin ?? "unknown";
  return origin === "real_provider";
}

export function needsReanalysisWarning(data: WholeBookAnalysisV2): boolean {
  const origin = data.analysis_metadata.result_origin;
  if (origin != null && origin !== "unknown" && origin !== "real_provider") {
    return true;
  }
  return hasScaffoldHeuristic(data);
}

export function parseWholeBookV2(raw: unknown): WholeBookAnalysisV2 {
  if (!obj(raw) || raw.schema_version !== "whole-book-analysis-v2.0") {
    throw new Error("WHOLE_BOOK_V2_SCHEMA_INVALID");
  }
  for (const key of [
    "book_metadata",
    "type_profile",
    "overview",
    "story",
    "characters",
    "suspense",
    "pacing",
    "chapters",
    "assessment",
    "evidence_index",
    "analysis_metadata",
  ]) {
    if (!obj(raw[key])) throw new Error(`WHOLE_BOOK_V2_${key.toUpperCase()}_INVALID`);
  }
  const r = raw as unknown as WholeBookAnalysisV2;
  if (
    !Array.isArray(r.characters.protagonist.stages) ||
    !Array.isArray(r.pacing.points) ||
    !Array.isArray(r.suspense.lifecycles) ||
    !Array.isArray(r.chapters.heatmap) ||
    !Array.isArray(r.assessment.dimensions)
  ) {
    throw new Error("WHOLE_BOOK_V2_COLLECTION_INVALID");
  }
  for (const [id, e] of Object.entries(r.evidence_index)) {
    if (id !== e.evidence_id || e.chapter_id === e.chapter_index) {
      throw new Error("WHOLE_BOOK_V2_EVIDENCE_IDENTITY_INVALID");
    }
  }
  const meta = r.analysis_metadata as WholeBookAnalysisV2["analysis_metadata"] & {
    result_origin?: unknown;
  };
  meta.result_origin = normalizeResultOrigin(meta.result_origin);
  return r;
}

export function parseProgressV2(raw: unknown): WholeBookProgressV2 {
  if (
    !obj(raw) ||
    raw.schema_version !== "whole-book-progress-v2.0" ||
    typeof raw.overall_percent !== "number" ||
    typeof raw.current_action !== "string"
  ) {
    throw new Error("WHOLE_BOOK_V2_PROGRESS_INVALID");
  }
  return raw as unknown as WholeBookProgressV2;
}

export const sevenModules = [
  "overview",
  "story",
  "characters",
  "suspense",
  "pacing",
  "chapters",
  "assessment",
] as const;
