import type { NarrativeReviewAction } from "./keys";
import type { WholeBookEvidenceRefDto } from "./evidence";

export type ConflictType =
  | "locked_asset_vs_new_run"
  | "candidate_contradiction"
  | "entity_identity"
  | "relation_conflict"
  | "evidence_stale"
  | "snapshot_mismatch"
  | "duplicate_asset_candidate";

export type ConflictSeverity = "info" | "warning" | "blocking";
export type ConflictStatus = "open" | "resolved" | "dismissed";

export interface ConflictRefDto {
  ref_type: string;
  ref_id: string;
  label: string;
  version: number | string | null;
}

export interface ConflictCenterItemDto {
  conflict_id: number | string;
  conflict_type: ConflictType;
  severity: ConflictSeverity;
  status: ConflictStatus;
  left_ref: ConflictRefDto;
  right_ref: ConflictRefDto;
  description: string;
  affected_modules: string[];
  affected_chapters: number[];
  evidence_refs: WholeBookEvidenceRefDto[];
  created_at: string;
  resolution: Record<string, unknown> | null;
  allowed_actions: NarrativeReviewAction[];
  defer_allowed: boolean;
}

export const BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN = true;
