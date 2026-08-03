/**
 * Typed client for Wave B whole-book foundation HTTP APIs.
 * Snapshot → Run → Windowing (no Provider calls).
 */
import { api } from "./apiClient";

export type SnapshotStatus = "building" | "completed" | "failed";

export type BookSnapshotMetadata = {
  snapshot_id: number;
  book_id: number;
  snapshot_version: number;
  status: SnapshotStatus | string;
  content_hash: string;
  chapter_count: number;
  paragraph_count: number;
  character_count: number;
  created_at: string | null;
  completed_at: string | null;
};

export type SnapshotChapterRow = {
  snapshot_chapter_id: number;
  snapshot_id: number;
  chapter_id: number;
  chapter_index: number;
  title: string;
  chapter_hash: string;
  paragraph_count: number;
  character_count: number;
};

export type SnapshotParagraphRow = {
  snapshot_paragraph_id: number;
  snapshot_id: number;
  snapshot_chapter_id: number;
  chapter_id: number;
  chapter_index: number;
  paragraph_index: number;
  global_paragraph_index: number;
  text: string;
  text_hash: string;
  character_count: number;
};

export type WholeBookInputUsage = {
  full_text_snapshot_used: boolean;
  chapter_analysis_asset_count: number;
  reader_journey_asset_count: number;
  confirmed_whole_book_asset_count: number;
};

export type WholeBookRunRecord = {
  run_id: number;
  book_id: number;
  snapshot_id: number | null;
  mode: string;
  status: string;
  current_stage_code: string | null;
  idempotency_key: string;
  engine_id: string;
  engine_version: string;
  contract_version: string;
  prompt_version: string | null;
  result_origin: string;
  input_usage: WholeBookInputUsage;
  consent_id: number | null;
  cost_policy_id: number | null;
  created_at: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
  failure_code: string | null;
  failure_message_safe: string | null;
};

export type WholeBookRunStageRow = {
  stage_id: number;
  run_id: number;
  stage_code: string;
  sequence: number;
  status: string;
  progress_current: number;
  progress_total: number;
  started_at: string | null;
  completed_at: string | null;
  last_error_code: string | null;
  last_error_message_safe: string | null;
};

export type WholeBookWindowRow = {
  window_id: number;
  run_id: number;
  snapshot_id: number;
  window_index: number;
  first_global_paragraph_index: number;
  last_global_paragraph_index: number;
  chapter_start_index: number;
  chapter_end_index: number;
  paragraph_count: number;
  character_count: number;
  token_estimate: number;
  overlap_before_paragraphs: number;
  overlap_after_paragraphs: number;
  window_hash: string;
  idempotency_key: string;
  status: string;
};

export type WholeBookWindowCoverage = {
  snapshot_id: number;
  run_id: number;
  total_paragraphs: number;
  covered_unique_paragraphs: number;
  duplicated_paragraphs: number;
  uncovered_paragraphs: number;
  coverage_ratio: number;
  order_valid: boolean;
  first_global_paragraph_index: number | null;
  last_global_paragraph_index: number | null;
};

export type GenerateWindowsResponse = {
  run_id: number;
  snapshot_id: number;
  reused: boolean;
  windowing_version: string;
  windows: WholeBookWindowRow[];
  coverage: WholeBookWindowCoverage;
  warnings: string[];
};

export type MinimalAnalysisSummary = {
  run_id: number;
  status: string;
  current_stage_code: string | null;
  completed_windows: number;
  total_windows: number;
  entity_count: number;
  asset_count: number;
  evidence_count: number;
  relation_count: number;
  provider_fixture_call_count: number;
  provider_real_call_count: number;
  overview_status: string | null;
};

export type ExecuteMinimalAnalysisFixtureResponse = {
  run: WholeBookRunRecord;
  summary: MinimalAnalysisSummary;
};

export type EntityAliasRow = {
  name: string;
  confidence: number;
  evidence_ids: number[];
};

export type NarrativeEntityRow = {
  entity_id: number;
  entity_type: string;
  canonical_name: string;
  aliases: EntityAliasRow[];
  state: string;
  confidence: number;
  evidence_count: number;
  event_count: number;
  character_profile?: NarrativeAssetRow | null;
  goals?: NarrativeAssetRow[];
  events?: NarrativeAssetRow[];
  linked_evidences?: NarrativeEvidenceRow[];
};

export type NarrativeAssetRow = {
  asset_id: number;
  asset_type: string;
  title: string;
  summary?: string | null;
  state: string;
  confidence: number;
  evidence_count: number;
  subject_entity_ids: number[];
  event_type?: string | null;
  chapters?: number[];
  participants?: string[];
  payload?: Record<string, unknown>;
  evidence_ids?: number[];
};

export type NarrativeEvidenceRow = {
  evidence_id: number;
  state: string;
  confidence: number;
  chapter_index?: number;
  paragraph_index?: number;
  global_paragraph_index?: number;
  quote_text?: string;
};

export type NarrativeRelationRow = {
  relation_id: number;
  relation_type: string;
  subject_kind: string;
  subject_id: number;
  object_kind: string;
  object_id: number;
  state: string;
  confidence: number;
  evidence_ids: number[];
};

export type EvidenceSourceDetail = {
  evidence_id: number;
  /** Real Chapter.id from API — never substitute chapter_index. */
  chapter_id: number | null;
  /** Display order only — never use as reader chapter id. */
  chapter_index: number;
  chapter_title: string;
  paragraph_index: number;
  global_paragraph_index: number;
  paragraph_text: string;
  quote_text: string;
  start_offset: number;
  end_offset: number;
  quote_hash?: string;
  paragraph_text_hash?: string;
  /** Snapshot / revision identity for stale checks. */
  snapshot_id?: number | null;
  state: string;
};

export type OverviewClaimAvailability = "available" | "unavailable" | "insufficient_evidence";

export type BookOverviewClaimRow = {
  claim_key: string;
  availability: OverviewClaimAvailability;
  summary: string | null;
  confidence: number | null;
  evidence_ids: number[];
  supporting_asset_ids: number[];
  conflict_ids: number[];
};

export type BookOverviewResultRow = {
  result_version: string;
  contract_version: string;
  run_id: number;
  book_id: number;
  snapshot_id: number;
  mode: string;
  result_origin: string;
  status: "completed" | "partial" | "unavailable";
  claims: BookOverviewClaimRow[];
  important_entity_ids: number[];
  key_event_asset_ids: number[];
  warnings: string[];
  created_at: string | null;
};

export const BOOK_OVERVIEW_CLAIM_LABELS: Record<string, string> = {
  genre_and_narrative_features: "小说类型及叙事特征",
  core_setting: "核心设定",
  protagonist: "主角",
  protagonist_core_goal: "主角核心目标",
  main_conflict: "主要矛盾",
  core_question: "核心悬念或问题",
  final_resolution: "最终解决",
  important_characters: "重要人物",
  key_events: "关键事件",
};

export const BOOK_OVERVIEW_CLAIM_ORDER = [
  "genre_and_narrative_features",
  "core_setting",
  "protagonist",
  "protagonist_core_goal",
  "main_conflict",
  "core_question",
  "final_resolution",
  "important_characters",
  "key_events",
] as const;

export const OTHER_ASSET_GROUPS: Array<{ asset_type: string; label: string }> = [
  { asset_type: "goal", label: "目标" },
  { asset_type: "conflict", label: "冲突" },
  { asset_type: "question", label: "悬念问题" },
  { asset_type: "setting_fact", label: "核心设定" },
];

export type CreateRunRequest = {
  snapshot_id: number;
  mode?: string;
  client_request_id: string;
  result_origin?: string;
};

export function newFoundationClientRequestId(prefix = "wb-diag"): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export const wholeBookFoundationApi = {
  createSnapshot: (bookId: number) =>
    api<{ snapshot: BookSnapshotMetadata; reused: boolean }>(
      `/api/v1/books/${bookId}/whole-book/snapshots`,
      { method: "POST" },
    ),

  listSnapshots: (bookId: number) =>
    api<{ snapshots: BookSnapshotMetadata[] }>(`/api/v1/books/${bookId}/whole-book/snapshots`),

  getSnapshot: (snapshotId: number) =>
    api<{ snapshot: BookSnapshotMetadata }>(`/api/v1/whole-book/snapshots/${snapshotId}`),

  listSnapshotChapters: (snapshotId: number) =>
    api<{ chapters: SnapshotChapterRow[] }>(
      `/api/v1/whole-book/snapshots/${snapshotId}/chapters`,
    ),

  listSnapshotParagraphs: (
    snapshotId: number,
    params?: { offset?: number; limit?: number; chapter_index?: number },
  ) => {
    const search = new URLSearchParams();
    if (params?.offset != null) search.set("offset", String(params.offset));
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.chapter_index != null) {
      search.set("chapter_index", String(params.chapter_index));
    }
    const qs = search.toString();
    return api<{
      paragraphs: SnapshotParagraphRow[];
      total: number;
      offset: number;
      limit: number;
    }>(`/api/v1/whole-book/snapshots/${snapshotId}/paragraphs${qs ? `?${qs}` : ""}`);
  },

  createRun: (bookId: number, body: CreateRunRequest) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/books/${bookId}/whole-book/runs`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listRuns: (bookId: number) =>
    api<{ runs: WholeBookRunRecord[] }>(`/api/v1/books/${bookId}/whole-book/runs`),

  getRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}`),

  listStages: (runId: number) =>
    api<{ stages: WholeBookRunStageRow[] }>(`/api/v1/whole-book/runs/${runId}/stages`),

  startRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}/start`, {
      method: "POST",
    }),

  pauseRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}/pause`, {
      method: "POST",
    }),

  resumeRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}/resume`, {
      method: "POST",
    }),

  cancelRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}/cancel`, {
      method: "POST",
    }),

  generateWindows: (runId: number) =>
    api<GenerateWindowsResponse>(`/api/v1/whole-book/runs/${runId}/windows/generate`, {
      method: "POST",
    }),

  listWindows: (runId: number) =>
    api<{ windows: WholeBookWindowRow[] }>(`/api/v1/whole-book/runs/${runId}/windows`),

  getWindowCoverage: (runId: number) =>
    api<{ coverage: WholeBookWindowCoverage }>(
      `/api/v1/whole-book/runs/${runId}/window-coverage`,
    ),

  executeMinimalAnalysisFixture: (runId: number) =>
    api<ExecuteMinimalAnalysisFixtureResponse>(
      `/api/v1/whole-book/runs/${runId}/minimal-analysis/execute-fixture`,
      { method: "POST" },
    ),

  getMinimalAnalysisSummary: (runId: number) =>
    api<{ summary: MinimalAnalysisSummary }>(
      `/api/v1/whole-book/runs/${runId}/minimal-analysis/summary`,
    ),

  listEntities: (runId: number) =>
    api<{ entities: NarrativeEntityRow[] }>(`/api/v1/whole-book/runs/${runId}/entities`),

  listAssets: (
    runId: number,
    params?: { asset_type?: string; entity_id?: number; offset?: number; limit?: number },
  ) => {
    const search = new URLSearchParams();
    if (params?.asset_type) search.set("asset_type", params.asset_type);
    if (params?.entity_id != null) search.set("entity_id", String(params.entity_id));
    if (params?.offset != null) search.set("offset", String(params.offset));
    if (params?.limit != null) search.set("limit", String(params.limit));
    const qs = search.toString();
    return api<{ assets: NarrativeAssetRow[]; total: number; offset: number; limit: number }>(
      `/api/v1/whole-book/runs/${runId}/assets${qs ? `?${qs}` : ""}`,
    );
  },

  listEvidences: (runId: number) =>
    api<{ evidences: NarrativeEvidenceRow[] }>(`/api/v1/whole-book/runs/${runId}/evidences`),

  listRelations: (runId: number) =>
    api<{ relations: NarrativeRelationRow[] }>(`/api/v1/whole-book/runs/${runId}/relations`),

  getOverview: (runId: number) =>
    api<{ overview: BookOverviewResultRow }>(`/api/v1/whole-book/runs/${runId}/overview`),

  getEvidenceSource: (evidenceId: number) =>
    api<{ source: EvidenceSourceDetail }>(`/api/v1/whole-book/evidences/${evidenceId}/source`),
};
