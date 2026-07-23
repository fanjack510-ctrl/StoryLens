import type {
  WholeBookAnalysisMode,
  WholeBookModuleKey,
  WholeBookModuleStatus,
} from "./keys";

export interface ConfidenceSummaryDto {
  mean: number | null;
  min: number | null;
  max: number | null;
  labeled_counts: Record<string, number>;
}

export interface ReviewSummaryDto {
  candidate_count: number;
  confirmed_count: number;
  corrected_count: number;
  rejected_count: number;
  locked_count: number;
  conflict_count: number;
}

/** Unified result envelope — frontend must not parse raw model JSON. */
export interface WholeBookResultEnvelope<TPayload = Record<string, unknown>> {
  schema: string;
  version: string;
  run_id: number;
  book_id: number;
  book_snapshot_id: number;
  analysis_mode: WholeBookAnalysisMode;
  module_key: WholeBookModuleKey;
  module_status: WholeBookModuleStatus;
  generated_at: string;
  source_stage_keys: string[];
  source_artifact_ids: string[];
  asset_ids: number[];
  asset_version_ids: number[];
  relation_ids: number[];
  relation_version_ids: number[];
  conflict_ids: number[];
  evidence_count: number;
  confidence_summary: ConfidenceSummaryDto;
  review_summary: ReviewSummaryDto;
  stale: boolean;
  partial: boolean;
  warnings: string[];
  payload: TPayload;
}

export const RESULT_ENVELOPE_SCHEMA = "whole_book_result_envelope";
export const RESULT_ENVELOPE_VERSION = "1";
