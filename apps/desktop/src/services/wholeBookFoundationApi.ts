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
};
