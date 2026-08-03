/**
 * ChapterFunctionsResultV2 — TypeScript SoT for Free product Desktop (CHG-20260803-041 / WB-2.2).
 * Wire contract_version = "v2" / package 2.0.0.
 * Chinese display labels MUST follow FUNCTION_LABEL_POLICY_FREEZE.md (not Prompt alternate copy).
 */

import type { CitedClaimV2, CoverageScopeV2 } from "./structureStagesResultV2";
import { COVERAGE_SCOPE_V2_VALUES, isCoverageScopeV2 } from "./structureStagesResultV2";

export type { CitedClaimV2, CoverageScopeV2 };
export { COVERAGE_SCOPE_V2_VALUES, isCoverageScopeV2 };

export const CHAPTER_FUNCTIONS_CONTRACT_ID = "ChapterFunctionsResultV2";
export const CHAPTER_FUNCTIONS_CONTRACT_PACKAGE_VERSION = "2.0.0";
export const CHAPTER_FUNCTIONS_WIRE_CONTRACT_VERSION = "v2";
export const CHAPTER_FUNCTIONS_EVIDENCE_CONTRACT_VERSION = "v2";

export const CHAPTER_FUNCTIONS_DEFAULT_LIMIT = 50;
export const CHAPTER_FUNCTIONS_MAX_LIMIT = 200;
/** @deprecated prefer CHAPTER_FUNCTIONS_DEFAULT_LIMIT — alias for API callers */
export const DEFAULT_LIMIT = CHAPTER_FUNCTIONS_DEFAULT_LIMIT;
/** @deprecated prefer CHAPTER_FUNCTIONS_MAX_LIMIT */
export const MAX_LIMIT = CHAPTER_FUNCTIONS_MAX_LIMIT;

/** CONTROLLED wire labels (FUNCTION_LABEL_POLICY_FREEZE). */
export const CANONICAL_FUNCTION_LABELS = [
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
] as const;

export type CanonicalFunctionLabel = (typeof CANONICAL_FUNCTION_LABELS)[number];

/**
 * Display-only Chinese mapping from FUNCTION_LABEL_POLICY_FREEZE.md.
 * Prompt alternate copy (e.g. 建立与铺垫) is NOT used — freeze wins.
 */
export const FUNCTION_LABEL_DISPLAY_ZH: Record<CanonicalFunctionLabel, string> = {
  setup: "开篇/建立",
  escalation: "冲突升级",
  climax: "高潮",
  resolution: "收束",
  transition: "过渡",
  side_story: "支线章",
  flashback: "回溯",
  empty: "空章/填充",
  non_mainline: "非主线",
  unknown: "未判定",
};

/** Freeze semantics notes for special labels (not bugs). */
export const FUNCTION_LABEL_SEMANTICS_ZH: Partial<Record<CanonicalFunctionLabel, string>> = {
  empty: "本章被判定为无明显叙事推进的空章或填充章，不是程序错误。",
  non_mainline: "本章主要为非主线内容，不等于分析失败。",
  unknown: "证据不足以可靠判定主要功能；wire 值为 unknown，不是系统异常。",
};

export function functionLabelDisplayZh(wire: string | null | undefined): string {
  if (wire == null || wire === "") return "—";
  const key = String(wire).trim().toLowerCase().replace(/-/g, "_");
  if ((CANONICAL_FUNCTION_LABELS as readonly string[]).includes(key)) {
    return FUNCTION_LABEL_DISPLAY_ZH[key as CanonicalFunctionLabel];
  }
  return wire;
}

export function isCanonicalFunctionLabel(value: unknown): value is CanonicalFunctionLabel {
  return typeof value === "string" && (CANONICAL_FUNCTION_LABELS as readonly string[]).includes(value);
}

export type ChapterFunctionItemV2 = {
  chapter_id: string | number;
  chapter_order: number;
  primary_function: string | null;
  secondary_functions: string[];
  observed_summary: CitedClaimV2;
  inferred_effect?: CitedClaimV2 | null;
  confidence: number;
  supporting_citation_ids: string[];
  limitations?: string[];
  chapter_title?: string | null;
};

export type ChapterFunctionsResultV2 = {
  contract_version: string;
  evidence_contract_version: string;
  coverage_scope: CoverageScopeV2 | string;
  chapters: ChapterFunctionItemV2[];
  analysis_confidence?: number | null;
  overall_confidence?: number | null;
  limitations?: string[];
  context_capabilities?: Record<string, unknown> | null;
  empty_reason?: string | null;
};

export type ChapterFunctionsProductResultStatus =
  | "completed"
  | "failed"
  | "conflict"
  | "canceled";

export type ChapterFunctionsCitationEvidenceBinding = {
  citation_id: string;
  evidence_id: number;
};

export type ChapterFunctionsConflictVersion = {
  version_id: string | number;
  label?: string | null;
  created_at?: string | null;
  state?: string | null;
};

/** Product envelope for GET .../chapter-functions (paginated). */
export type ChapterFunctionsProductResponse = {
  result_status: ChapterFunctionsProductResultStatus | string;
  contract_version?: string | null;
  schema_version?: string | null;
  coverage_scope: CoverageScopeV2 | string | null;
  /** Full V2 object when present; may be null on failed/canceled/absent paths. */
  chapter_functions: ChapterFunctionsResultV2 | null;
  /** Paginated chapter items (server page). */
  items: ChapterFunctionItemV2[];
  next_cursor?: string | null;
  total_chapters?: number | null;
  failure_code?: string | null;
  empty_reason?: string | null;
  failure_message_safe?: string | null;
  source_revision?: {
    run_id: number;
    snapshot_id?: number | null;
    snapshot_revision?: string | null;
    book_id?: number | null;
  } | null;
  conflict?: {
    versions: ChapterFunctionsConflictVersion[];
    current_pointer?: string | number | null;
  } | null;
  evidence_references?: string[];
  fixture_test_data?: boolean;
  /**
   * Product-layer citation → evidence_id bindings.
   * NOT an evidence_map wrapper inside ChapterFunctionsResultV2.
   */
  citation_evidence_bindings?: ChapterFunctionsCitationEvidenceBinding[];
  /** Optional unfinished counts for partial UX. */
  unfinished_chapter_count?: number | null;
  analyzed_chapter_count?: number | null;
  product_result_status?: string | null;
};

export type ChapterFunctionsClientViewState =
  | "available"
  | "partial"
  | "insufficient"
  | "failed"
  | "canceled"
  | "conflict"
  | "loading"
  | "absent"
  | "unsupported_contract"
  | "network_error"
  | "not_started";

export class UnsupportedChapterFunctionsContractError extends Error {
  readonly code = "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED";
  readonly contractVersion: string;

  constructor(contractVersion: string) {
    super(`Unsupported chapter_functions contract_version: ${contractVersion}`);
    this.name = "UnsupportedChapterFunctionsContractError";
    this.contractVersion = contractVersion;
  }
}

/**
 * Lab V1 adapter payload — NOT Free product SoT.
 * Namespaced to avoid collision with Free V2 / Pro Insights.
 */
export type LabChapterFunctionsResultV1 = {
  items: Array<{
    chapter_id: number | string;
    chapter_order: number;
    function_labels: string[];
    primary_storyline_ids?: number[];
    character_focus_ids?: number[];
    hook_ids?: number[];
    payoff_ids?: number[];
    change_summary?: string;
    evidence_refs?: unknown[];
  }>;
  contract_version: "v1" | string;
  adapted_from: "ChapterFunctionsResultV2" | string;
  coverage_scope?: string | null;
  result_status?: string | null;
};

/**
 * Pro Insights chapter-functions naming — FORBIDDEN as Free SoT.
 * Kept only to isolate namespace collisions in Desktop.
 */
export type ProInsightsChapterFunctionsResultV1 = {
  readonly __namespace: "pro_insights";
  readonly forbidden_as_free_sot: true;
};

export function assertChapterFunctionsResultV2(raw: unknown): ChapterFunctionsResultV2 {
  if (!raw || typeof raw !== "object") {
    throw new UnsupportedChapterFunctionsContractError("missing");
  }
  const obj = raw as Record<string, unknown>;
  const contractVersion = String(obj.contract_version ?? "");
  if (
    contractVersion !== CHAPTER_FUNCTIONS_WIRE_CONTRACT_VERSION &&
    contractVersion !== CHAPTER_FUNCTIONS_CONTRACT_PACKAGE_VERSION
  ) {
    throw new UnsupportedChapterFunctionsContractError(contractVersion || "missing");
  }
  const evidenceVersion = String(obj.evidence_contract_version ?? "");
  if (
    evidenceVersion &&
    evidenceVersion !== CHAPTER_FUNCTIONS_EVIDENCE_CONTRACT_VERSION &&
    evidenceVersion !== CHAPTER_FUNCTIONS_CONTRACT_PACKAGE_VERSION
  ) {
    throw new UnsupportedChapterFunctionsContractError(`evidence:${evidenceVersion || "missing"}`);
  }
  if (!Array.isArray(obj.chapters)) {
    throw new Error("CHAPTER_FUNCTIONS_DTO_INVALID: chapters must be an array");
  }
  const coverage = String(obj.coverage_scope ?? "");
  if (!isCoverageScopeV2(coverage)) {
    throw new Error(`CHAPTER_FUNCTIONS_COVERAGE_SCOPE_INVALID: ${coverage}`);
  }
  return obj as ChapterFunctionsResultV2;
}

export function resolveEvidenceIdForCitation(
  citationId: string,
  bindings: ChapterFunctionsCitationEvidenceBinding[] | undefined,
): number | null {
  if (!bindings?.length) return null;
  const hit = bindings.find((b) => b.citation_id === citationId);
  return hit?.evidence_id ?? null;
}

export function collectChapterEvidenceCitationIds(item: ChapterFunctionItemV2): string[] {
  const ids = [
    ...(item.supporting_citation_ids ?? []),
    ...(item.observed_summary?.citation_ids ?? []),
    ...(item.inferred_effect?.citation_ids ?? []),
  ];
  return [...new Set(ids.filter(Boolean))];
}

export function firstEvidenceIdForChapter(
  item: ChapterFunctionItemV2,
  bindings: ChapterFunctionsCitationEvidenceBinding[] | undefined,
): number | null {
  for (const cid of collectChapterEvidenceCitationIds(item)) {
    const eid = resolveEvidenceIdForCitation(cid, bindings);
    if (eid != null) return eid;
  }
  return null;
}

export function deriveChapterFunctionsViewState(args: {
  runStatus: string | null | undefined;
  fetchStatus: "idle" | "pending" | "success" | "error";
  httpStatus?: number | null;
  errorCode?: string | null;
  response?: ChapterFunctionsProductResponse | null;
  unsupportedContract?: boolean;
  networkError?: boolean;
}): ChapterFunctionsClientViewState {
  const {
    runStatus,
    fetchStatus,
    httpStatus,
    errorCode,
    response,
    unsupportedContract,
    networkError,
  } = args;

  if (!runStatus || runStatus === "pending") return "not_started";
  if (runStatus === "running" || runStatus === "paused" || runStatus === "recoverable") {
    return "loading";
  }
  if (runStatus === "cancelled" || runStatus === "canceled") return "canceled";
  if (runStatus === "failed") return "failed";

  if (unsupportedContract) return "unsupported_contract";
  if (networkError) return "network_error";
  if (fetchStatus === "pending") return "loading";

  if (
    httpStatus === 404 ||
    errorCode === "CHAPTER_FUNCTIONS_RESULT_ABSENT" ||
    errorCode === "CHAPTER_FN_RESULT_ABSENT"
  ) {
    return "absent";
  }

  if (fetchStatus === "error") {
    if (
      errorCode === "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED" ||
      errorCode === "CHAPTER_FN_UNSUPPORTED_VERSION"
    ) {
      return "unsupported_contract";
    }
    return "network_error";
  }

  if (!response) return "absent";

  if (response.result_status === "failed") return "failed";
  if (response.result_status === "canceled") return "canceled";
  if (response.result_status === "conflict") return "conflict";

  if (
    response.failure_code === "CHAPTER_FN_UNSUPPORTED_VERSION" ||
    response.failure_code === "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED"
  ) {
    return "unsupported_contract";
  }

  const scope =
    response.coverage_scope ??
    response.chapter_functions?.coverage_scope ??
    null;
  const productStatus = response.product_result_status;

  if (scope === "insufficient" || productStatus === "insufficient") {
    return "insufficient";
  }

  if (
    scope === "partial_span" ||
    productStatus === "partial" ||
    (response.unfinished_chapter_count != null && response.unfinished_chapter_count > 0)
  ) {
    const hasItems =
      (response.items?.length ?? 0) > 0 ||
      (response.chapter_functions?.chapters?.length ?? 0) > 0;
    if (hasItems) return "partial";
  }

  const hasItems =
    (response.items?.length ?? 0) > 0 ||
    (response.chapter_functions?.chapters?.length ?? 0) > 0;
  if (response.result_status === "completed" && hasItems) {
    return "available";
  }

  if (scope === "insufficient") return "insufficient";
  return "absent";
}

export function clampChapterFunctionsLimit(limit?: number | null): number {
  const n = limit == null ? CHAPTER_FUNCTIONS_DEFAULT_LIMIT : Number(limit);
  if (!Number.isFinite(n) || n < 1) return CHAPTER_FUNCTIONS_DEFAULT_LIMIT;
  return Math.min(Math.floor(n), CHAPTER_FUNCTIONS_MAX_LIMIT);
}
