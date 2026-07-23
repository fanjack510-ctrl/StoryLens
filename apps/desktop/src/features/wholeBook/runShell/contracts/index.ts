/** Phase 2A-P run shell frontend contract exports. */

export * from "./mockLab";
export * from "./createRun";
export * from "./runState";
export * from "./polling";
export * from "./actions";
export * from "./errors";
export * from "./guards";

export const LAB_API_ROUTES = [
  ["POST", "/api/v1/labs/whole-book-runs"],
  ["GET", "/api/v1/labs/whole-book-runs/{run_id}"],
  ["GET", "/api/v1/labs/whole-book-runs/{run_id}/stages"],
  ["POST", "/api/v1/labs/whole-book-runs/{run_id}/pause"],
  ["POST", "/api/v1/labs/whole-book-runs/{run_id}/resume"],
  ["POST", "/api/v1/labs/whole-book-runs/{run_id}/cancel"],
  ["POST", "/api/v1/labs/whole-book-runs/{run_id}/stages/{stage_key}/retry"],
] as const;

export const ORDERED_MOCK_STAGE_KEYS = [
  "build_fulltext_index",
  "resolve_entities",
  "analyze_structure",
  "analyze_storylines",
  "analyze_characters",
  "analyze_hooks",
  "analyze_causality_timeline",
  "generate_diagnostics",
  "verify_evidence",
  "persist_narrative_assets",
] as const;
