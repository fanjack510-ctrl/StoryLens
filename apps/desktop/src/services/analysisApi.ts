import { api, getApiBase } from "./apiClient";
import type { Run, RunResults, Scene, SceneParagraphs, SceneResultItem } from "../types";
export const analysisApi = {
  preflight: (payload: any) => api<any>("/api/v1/analysis-runs/preflight", {
    method: "POST", body: JSON.stringify(payload),
  }),
  runs: () => api<Run[]>("/api/v1/analysis-runs"),
  run: (id: number) => api<Run>(`/api/v1/analysis-runs/${id}`),
  results: (runId: number) =>
    api<RunResults>(`/api/v1/analysis-runs/${runId}/results`),
  sceneAnalysis: (sceneId: number | string) =>
    api<SceneResultItem>(`/api/v1/scenes/${sceneId}/analysis`),
  sceneParagraphs: (sceneId: number | string) =>
    api<SceneParagraphs>(`/api/v1/scenes/${sceneId}/paragraphs`),
  resultsExportUrl: (runId: number, format: "json" | "markdown") =>
    `${getApiBase()}/api/v1/analysis-runs/${runId}/results/export?format=${format}`,
  scenes: (chapter: number) =>
    api<Scene[]>(`/api/v1/chapters/${chapter}/scenes`),
  artifacts: (scene: string | number) =>
    api<any[]>(`/api/v1/scenes/${scene}/analysis-artifacts`),
  evidence: (artifact: number) =>
    api<any[]>(`/api/v1/artifacts/${artifact}/evidence`),
  start: (chapter: number, payload: any) =>
    api<{ run_id: number }>(`/api/v1/chapters/${chapter}/analysis-runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  retry: (run: number) =>
    api(`/api/v1/analysis-runs/${run}/retry`, { method: "POST" }),
  resumeSceneAnalysis: (
    run: number,
    payload?: {
      client_request_id: string;
      cloud_consent: boolean;
      confirmed: boolean;
      provider_state_version?: string;
    },
  ) =>
    api<{ run_id: number; status: string }>(`/api/v1/analysis-runs/${run}/resume-scene-analysis`, {
      method: "POST",
      body: JSON.stringify(
        payload || {
          client_request_id: crypto.randomUUID(),
          cloud_consent: true,
          confirmed: true,
        },
      ),
    }),
  replaySceneAnalysisOffline: (
    run: number,
    payload?: {
      scene_id?: number;
      invocation_id?: number;
      confirmed?: boolean;
      client_request_id?: string;
    },
  ) =>
    api<{
      run_id: number;
      scene_id: number;
      artifact_id: number;
      invocation_id: number;
      status: string;
      completed_scene_count: number;
      remaining_scene_count: number;
      remaining_scene_ids: number[];
      offline_replay_available: boolean;
      idempotent_replay: boolean;
      message: string;
      http_request_sent: boolean;
      request_id?: string | null;
    }>(`/api/v1/analysis-runs/${run}/scene-analysis/offline-replay`, {
      method: "POST",
      body: JSON.stringify({ confirmed: true, ...payload }),
    }),
  sceneAnalysisResumePreflight: (run: number, payload?: { cloud_consent?: boolean }) =>
    api<{
      run_id: number;
      boundary_revision_id: number | null;
      total_scene_count: number;
      completed_scene_count: number;
      remaining_scene_count: number;
      remaining_scene_ids: number[];
      expected_requests: number;
      worst_case_requests: number;
      estimated_tokens: number;
      worst_case_tokens: number;
      estimated_cost: number;
      worst_case_cost: number;
      remaining_budget: Record<string, number>;
      within_budget: boolean;
      exceeded_dimensions: string[];
      provider_state_version: string;
      provider_name: string;
      eligible: boolean;
      blockers: string[];
      requires_cloud_consent: boolean;
      estimated: boolean;
      currency: string;
      coverage_rate?: number | null;
    }>(
      payload
        ? `/api/v1/analysis-runs/${run}/resume-scene-analysis/preflight`
        : `/api/v1/analysis-runs/${run}/resume-scene-analysis/preflight`,
      payload
        ? { method: "POST", body: JSON.stringify(payload) }
        : { method: "GET" },
    ),
  invocations: (run: number) =>
    api<any[]>(`/api/v1/analysis-runs/${run}/model-invocations`),
  recoveryPreflight: (run: number) =>
    api<any>(`/api/v1/analysis-runs/${run}/recovery-preflight`),
  recoverPreflight: (run: number, payload: { cloud_consent: boolean }) =>
    api<{
      source_run_id: number;
      provider_name: string;
      eligible: boolean;
      blockers: string[];
      provider_state_version: string;
      capability_schema_version: string;
      health_state: string;
      health_source: string;
      reused_batch_count: number;
      remaining_batch_count: number;
      expected_requests: number;
      worst_case_requests: number;
      estimated_tokens: number;
      worst_case_tokens: number;
      estimated_cost: number;
      worst_case_cost: number;
      currency: string;
      remaining_budget: Record<string, number>;
      within_budget: boolean;
      exceeded_dimensions: string[];
      requires_cloud_consent: boolean;
    }>(`/api/v1/analysis-runs/${run}/recover/preflight`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  continueFromCheckpoints: (
    run: number,
    payload: {
      client_request_id: string;
      cloud_consent: boolean;
      confirmed: boolean;
      provider_state_version?: string;
    },
  ) =>
    api<{
      run_id: number;
      recovered_from_run_id: number;
      status: string;
      reused_batch_count: number;
      remaining_batch_count: number;
      reservation_id?: number;
      request_id?: string;
      idempotent_replay?: boolean;
    }>(`/api/v1/analysis-runs/${run}/recover`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  boundaryReview: (book: number, chapter: number) =>
    api<any>(`/api/v1/books/${book}/chapters/${chapter}/boundary-review`),
  decideBoundary: (
    review: number,
    transition: string,
    user_decision: string,
    manual_reason_type?: string,
    user_reason?: string,
  ) =>
    api<any>(`/api/v1/boundary-reviews/${review}/decisions/${transition}`, {
      method: "PUT",
      body: JSON.stringify({ user_decision, manual_reason_type, user_reason }),
    }),
  addManualBoundary: (review: number, left_paragraph_id: string) =>
    api<any>(`/api/v1/boundary-reviews/${review}/manual-boundaries`, {
      method: "POST", body: JSON.stringify({ left_paragraph_id }),
    }),
  deleteManualBoundary: (review: number, transition: string) =>
    api(`/api/v1/boundary-reviews/${review}/manual-boundaries/${encodeURIComponent(transition)}`, { method: "DELETE" }),
  scenePreview: (review: number) => api<any>(`/api/v1/boundary-reviews/${review}/scene-preview`),
  sceneAnalysisPreflight: (review: number) =>
    api<any>(`/api/v1/boundary-reviews/${review}/scene-analysis-preflight`),
  confirmReview: (review: number, confirmed_by: string) =>
    api<any>(`/api/v1/boundary-reviews/${review}/confirm`, {
      method: "POST", body: JSON.stringify({ confirmed_by }),
    }),
  readerJourneyPreflight: (runId: number, payload?: { cloud_consent?: boolean }) =>
    api<import("../types").ReaderJourneyPreflight>(
      `/api/v1/analysis-runs/${runId}/reader-journey/preflight`,
      { method: "POST", body: JSON.stringify(payload || {}) },
    ),
  createReaderJourney: (
    runId: number,
    payload: {
      client_request_id: string;
      cloud_consent: boolean;
      confirmed?: boolean;
      force_new_version?: boolean;
    },
  ) =>
    api<import("../types").ReaderJourneyAccepted>(
      `/api/v1/analysis-runs/${runId}/reader-journey`,
      { method: "POST", body: JSON.stringify({ confirmed: true, ...payload }) },
    ),
  readerJourney: (runId: number) =>
    api<import("../types").ReaderJourneyResult | null>(
      `/api/v1/analysis-runs/${runId}/reader-journey`,
    ),
  readerJourneyProgress: (journeyRunId: number) =>
    api<import("../types").ReaderJourneyProgress>(
      `/api/v1/reader-journey-runs/${journeyRunId}/progress`,
    ),
  resumeReaderJourney: (
    journeyRunId: number,
    payload: { client_request_id: string; cloud_consent: boolean; confirmed?: boolean },
  ) =>
    api<import("../types").ReaderJourneyAccepted>(
      `/api/v1/reader-journey-runs/${journeyRunId}/resume`,
      { method: "POST", body: JSON.stringify({ confirmed: true, ...payload }) },
    ),
  offlineReplayReaderJourney: (
    journeyRunId: number,
    payload?: { invocation_ids?: number[]; confirmed?: boolean },
  ) =>
    api<{
      journey_run_id: number;
      replayed_scene_ids: number[];
      completed_count: number;
      remaining_count: number;
      source_invocation_ids: number[];
      migrated_from_contract_version?: string | null;
      current_contract_version: string;
      http_requests: number;
      tokens: number;
      cost: number;
      idempotent_replay: boolean;
      errors?: string[];
    }>(`/api/v1/reader-journey-runs/${journeyRunId}/scene-profiles/offline-replay`, {
      method: "POST",
      body: JSON.stringify({ confirmed: true, ...payload }),
    }),
  semanticRecalibrateReaderJourney: (
    journeyRunId: number,
    payload?: { confirmed?: boolean },
  ) =>
    api<{
      journey_run_id: number;
      calibrated_profile_count: number;
      empty_qin_remaining: number;
      journey_nodes: Array<{
        scene_id: number;
        scene_ordinal: number;
        paragraph_count: number;
        role: string;
        label: string;
        primary_question?: string;
      }>;
      question_chain_count: number;
      one_sentence_diagnosis: string;
      scene_contract_version: string;
      http_requests: number;
      tokens: number;
      cost: number;
    }>(`/api/v1/reader-journey-runs/${journeyRunId}/semantic-recalibrate`, {
      method: "POST",
      body: JSON.stringify({ confirmed: true, ...payload }),
    }),
  readerJourneyExportUrl: (journeyRunId: number) =>
    `${getApiBase()}/api/v1/reader-journey-runs/${journeyRunId}/export?format=json`,
};
