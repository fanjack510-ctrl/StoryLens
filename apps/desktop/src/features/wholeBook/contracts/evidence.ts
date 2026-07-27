import type { EvidenceIntegrityStatus } from "./keys";

export type EvidenceRole = "support" | "contradict" | "context";

export interface WholeBookEvidenceRefDto {
  evidence_id: number | string;
  evidence_type: string;
  book_snapshot_id: number;
  snapshot_chapter_id: number | null;
  snapshot_paragraph_id: number | null;
  source_chapter_id: number | null;
  source_scene_id: number | null;
  stable_paragraph_id: string | null;
  paragraph_content_hash: string;
  start_offset: number | null;
  end_offset: number | null;
  evidence_role: EvidenceRole;
  evidence_label: string;
  chapter_title: string;
  paragraph_preview: string;
  deep_link: string;
  integrity_status: EvidenceIntegrityStatus;
}

export const MAX_PARAGRAPH_PREVIEW_CHARS = 160;
