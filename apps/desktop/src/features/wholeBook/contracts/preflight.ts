import type { WholeBookAnalysisMode, WholeBookModuleKey } from "./keys";

export interface PreflightBookStatusDto {
  book_id: number;
  title: string;
  chapter_count: number;
  paragraph_count: number;
  character_count: number;
  current_snapshot_id: number | null;
  snapshot_created_at: string | null;
  body_changed_since_snapshot: boolean;
  snapshot_rebuild_required: boolean;
}

export interface PreflightSnapshotStatusDto {
  snapshot_id: number | null;
  status: string | null;
  created_at: string | null;
  chapter_count: number;
  paragraph_count: number;
  character_count: number;
  integrity_ok: boolean;
}

export interface PreflightCapabilityStatusDto {
  capability_key: string;
  allowed: boolean;
  reason_code: string;
  availability: string;
  message: string;
}

export interface PreflightQuotaStatusDto {
  allowed: boolean;
  reason_code: string;
  remaining: Record<string, unknown>;
  estimated_usage: Record<string, unknown>;
}

export interface PreflightEngineStatusDto {
  engine_id: string | null;
  available: boolean;
  supports_mode: boolean;
  message: string;
}

export interface PreflightStagePlanItemDto {
  stage_key: string;
  display_name: string;
  order: number;
  required: boolean;
  estimated_cost_class: string;
  produced_module_keys: string[];
}

export interface PreflightSourceCoverageDto {
  fulltext_snapshot_ready: boolean;
  enhanced_asset_coverage_ratio: number | null;
  scene_coverage_ratio: number | null;
  reader_journey_coverage_ratio: number | null;
  chapter_analysis_coverage_ratio: number | null;
  enhanced_degraded: boolean;
}

export interface PreflightEstimatedUsageDto {
  estimated_token_input: number | null;
  estimated_token_output: number | null;
  estimated_cost: number | null;
  estimated_duration_class: string;
  currency: string;
}

export interface WholeBookPreflightPageModel {
  book: PreflightBookStatusDto;
  snapshot: PreflightSnapshotStatusDto;
  capability: PreflightCapabilityStatusDto;
  quota: PreflightQuotaStatusDto;
  engine: PreflightEngineStatusDto;
  analysis_mode: WholeBookAnalysisMode;
  requested_modules: WholeBookModuleKey[];
  resolved_modules: WholeBookModuleKey[];
  stage_plan: PreflightStagePlanItemDto[];
  source_coverage: PreflightSourceCoverageDto;
  estimated_usage: PreflightEstimatedUsageDto;
  blocking_reasons: string[];
  warnings: string[];
  run_creation_enabled: boolean;
  confirmation_required: boolean;
  auto_fill_notes: string[];
  /** Must always be false — no force-start bypass. */
  force_start_allowed: false;
}
