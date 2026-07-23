import type { NarrativeReviewAction } from "./keys";

export type ReviewTargetType =
  | "asset"
  | "asset_version"
  | "relation"
  | "relation_version"
  | "conflict"
  | "module_result";

export interface NarrativeReviewActionRequest {
  action: NarrativeReviewAction;
  target_type: ReviewTargetType;
  target_id: string;
  expected_version: number | string;
  actor: string;
  correction_payload: Record<string, unknown>;
  evidence_changes: Record<string, unknown>[];
  resolution_payload: Record<string, unknown>;
  reason: string | null;
  idempotency_key: string;
}

export interface NarrativeReviewAuditContract {
  action: NarrativeReviewAction;
  target_type: ReviewTargetType;
  target_id: string;
  actor: string;
  idempotency_key: string;
  reason: string | null;
  created_at: string | null;
}
