/**
 * StructureStagesResultV2 — TypeScript SoT for Free product Desktop (CHG-20260801-035).
 * Wire contract_version = "v2" / package 2.0.0.
 * Must stay aligned with frozen STRUCTURE_CONTRACT_V2_FREEZE — do not invent fields.
 */

export const STRUCTURE_STAGES_CONTRACT_ID = "StructureStagesResultV2";
export const STRUCTURE_STAGES_CONTRACT_PACKAGE_VERSION = "2.0.0";
export const STRUCTURE_STAGES_WIRE_CONTRACT_VERSION = "v2";
export const STRUCTURE_STAGES_EVIDENCE_CONTRACT_VERSION = "v2";

export type CoverageScopeV2 =
  | "local"
  | "partial_span"
  | "full_selected_range"
  | "insufficient";

export const COVERAGE_SCOPE_V2_VALUES: readonly CoverageScopeV2[] = [
  "local",
  "partial_span",
  "full_selected_range",
  "insufficient",
] as const;

export type ClaimStatusV2 = "observed" | "inferred" | "not_observed";

export type CitedClaimV2 = {
  value: string | null;
  status: ClaimStatusV2 | string;
  citation_ids: string[];
  confidence?: number | null;
};

export type CitedBoundaryV2 = {
  citation_ids: string[];
  value?: string | null;
  note?: string | null;
  status?: string | null;
  confidence?: number | null;
};

export type StructureStageV2 = {
  local_stage_ref: string;
  title: string;
  summary: CitedClaimV2;
  start_boundary: CitedBoundaryV2;
  end_boundary: CitedBoundaryV2;
  order_index?: number;
  stage_type?: string;
  supporting_citation_ids?: string[];
  related_turning_point_refs?: string[];
  narrative_function?: string | null;
  confidence?: number | null;
  stage_key?: string | null;
  chapter_range?: [number | null, number | null] | (number | null)[];
};

export type TurningPointV2 = {
  local_turning_point_ref: string;
  title: string;
  description: CitedClaimV2;
  citation_ids?: string[];
  order_index?: number;
  turning_point_type?: string;
  before_state?: string | null;
  after_state?: string | null;
  impact?: string | null;
  related_stage_refs?: string[];
  confidence?: number | null;
  turning_point_key?: string | null;
  chapter_id?: number | null;
};

export type StructureStagesResultV2 = {
  contract_version: string;
  evidence_contract_version: string;
  coverage_scope: CoverageScopeV2 | string;
  stages: StructureStageV2[];
  turning_points: TurningPointV2[];
  analysis_confidence?: number | null;
  overall_confidence?: number | null;
  limitations?: string[];
  context_capabilities?: Record<string, unknown> | null;
};

export type StructureProductResultStatus =
  | "completed"
  | "failed"
  | "conflict"
  | "canceled";

export type StructureCitationEvidenceBinding = {
  citation_id: string;
  evidence_id: number;
};

export type StructureConflictVersion = {
  version_id: string | number;
  label?: string | null;
  created_at?: string | null;
  state?: string | null;
};

/** Product envelope for GET /api/v1/whole-book/runs/{run_id}/structure */
export type StructureProductResponse = {
  result_status: StructureProductResultStatus;
  coverage_scope: CoverageScopeV2 | string | null;
  structure: StructureStagesResultV2 | null;
  failure_code?: string | null;
  empty_reason?: string | null;
  failure_message_safe?: string | null;
  source_revision?: {
    run_id: number;
    snapshot_id?: number | null;
    snapshot_revision?: string | null;
  } | null;
  conflict?: {
    versions: StructureConflictVersion[];
    current_pointer?: string | number | null;
  } | null;
  /**
   * Product-layer citation → evidence_id bindings for Wave D deep link.
   * NOT an evidence_map wrapper inside StructureStagesResultV2.
   */
  citation_evidence_bindings?: StructureCitationEvidenceBinding[];
};

export type StructureClientViewState =
  | "available"
  | "insufficient"
  | "loading"
  | "failed"
  | "canceled"
  | "conflict"
  | "absent"
  | "unsupported_contract"
  | "network_error"
  | "not_started";

export class UnsupportedStructureContractError extends Error {
  readonly code = "STRUCTURE_CONTRACT_UNSUPPORTED";
  readonly contractVersion: string;

  constructor(contractVersion: string) {
    super(`Unsupported structure contract_version: ${contractVersion}`);
    this.name = "UnsupportedStructureContractError";
    this.contractVersion = contractVersion;
  }
}

export function isCoverageScopeV2(value: unknown): value is CoverageScopeV2 {
  return typeof value === "string" && (COVERAGE_SCOPE_V2_VALUES as readonly string[]).includes(value);
}

export function assertStructureStagesResultV2(
  raw: unknown,
): StructureStagesResultV2 {
  if (!raw || typeof raw !== "object") {
    throw new UnsupportedStructureContractError("missing");
  }
  const obj = raw as Record<string, unknown>;
  const contractVersion = String(obj.contract_version ?? "");
  if (contractVersion !== STRUCTURE_STAGES_WIRE_CONTRACT_VERSION) {
    throw new UnsupportedStructureContractError(contractVersion || "missing");
  }
  const evidenceVersion = String(obj.evidence_contract_version ?? "");
  if (evidenceVersion !== STRUCTURE_STAGES_EVIDENCE_CONTRACT_VERSION) {
    throw new UnsupportedStructureContractError(
      `evidence:${evidenceVersion || "missing"}`,
    );
  }
  if (!Array.isArray(obj.stages) || !Array.isArray(obj.turning_points)) {
    throw new Error("STRUCTURE_DTO_INVALID: stages/turning_points must be arrays");
  }
  const coverage = String(obj.coverage_scope ?? "");
  if (!isCoverageScopeV2(coverage)) {
    throw new Error(`STRUCTURE_COVERAGE_SCOPE_INVALID: ${coverage}`);
  }
  return obj as StructureStagesResultV2;
}

export function resolveEvidenceIdForCitation(
  citationId: string,
  bindings: StructureCitationEvidenceBinding[] | undefined,
): number | null {
  if (!bindings?.length) return null;
  const hit = bindings.find((b) => b.citation_id === citationId);
  return hit?.evidence_id ?? null;
}

export function collectStageEvidenceCitationIds(stage: StructureStageV2): string[] {
  const ids = [
    ...(stage.summary?.citation_ids ?? []),
    ...(stage.start_boundary?.citation_ids ?? []),
    ...(stage.end_boundary?.citation_ids ?? []),
    ...(stage.supporting_citation_ids ?? []),
  ];
  return [...new Set(ids.filter(Boolean))];
}

export function collectTurningPointEvidenceCitationIds(tp: TurningPointV2): string[] {
  const ids = [
    ...(tp.description?.citation_ids ?? []),
    ...(tp.citation_ids ?? []),
  ];
  return [...new Set(ids.filter(Boolean))];
}

export function stageChapterRange(
  stage: StructureStageV2,
): { start: number | null; end: number | null } {
  const range = stage.chapter_range;
  if (Array.isArray(range) && range.length >= 2) {
    const start = range[0] == null ? null : Number(range[0]);
    const end = range[1] == null ? null : Number(range[1]);
    return {
      start: Number.isFinite(start as number) ? (start as number) : null,
      end: Number.isFinite(end as number) ? (end as number) : null,
    };
  }
  return { start: null, end: null };
}

export function deriveStructureViewState(args: {
  runStatus: string | null | undefined;
  fetchStatus: "idle" | "pending" | "success" | "error";
  httpStatus?: number | null;
  errorCode?: string | null;
  response?: StructureProductResponse | null;
  unsupportedContract?: boolean;
  networkError?: boolean;
}): StructureClientViewState {
  const { runStatus, fetchStatus, httpStatus, errorCode, response, unsupportedContract, networkError } =
    args;

  if (!runStatus || runStatus === "pending") return "not_started";
  if (runStatus === "running" || runStatus === "paused" || runStatus === "recoverable") {
    return "loading";
  }
  if (runStatus === "cancelled" || runStatus === "canceled") return "canceled";
  if (runStatus === "failed") return "failed";

  if (unsupportedContract) return "unsupported_contract";
  if (networkError) return "network_error";
  if (fetchStatus === "pending") return "loading";

  if (httpStatus === 404 || errorCode === "STRUCTURE_RESULT_ABSENT") {
    return "absent";
  }

  if (fetchStatus === "error") {
    if (errorCode === "STRUCTURE_CONTRACT_UNSUPPORTED") return "unsupported_contract";
    return "network_error";
  }

  if (!response) return "absent";

  if (response.result_status === "failed") return "failed";
  if (response.result_status === "canceled") return "canceled";
  if (response.result_status === "conflict") return "conflict";

  const scope = response.coverage_scope ?? response.structure?.coverage_scope;
  if (scope === "insufficient") return "insufficient";

  if (response.structure && (response.structure.stages?.length ?? 0) > 0) {
    return "available";
  }

  if (scope === "insufficient") return "insufficient";
  return "absent";
}
