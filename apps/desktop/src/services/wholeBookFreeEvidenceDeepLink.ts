/**
 * Evidence deep-link for Wave D Free whole-book product.
 * Reuses BookRoutePage reader with offset highlight query params.
 * No fuzzy fallback / no evidence_map wrapper.
 * chapter_id is the real Chapter.id — never fall back to chapter_index.
 */
import type { EvidenceSourceDetail } from "./wholeBookFoundationApi";

export type WholeBookEvidenceReaderParams = {
  evidenceId: number;
  chapterId: number;
  paragraphIndex: number;
  startOffset: number;
  endOffset: number;
};

export type WholeBookEvidenceRestoreState = {
  restoreFunction?: string | null;
  restoreStatus?: string | null;
  restoreCursor?: string | null;
  restoreChapter?: string | null;
};

export type WholeBookEvidenceDeepLinkOptions = {
  /** Preserve Free module after returning from reader. */
  returnModule?: string;
  /** Chapter Functions restore anchors (persisted across reader round-trip). */
  restore?: WholeBookEvidenceRestoreState;
};

export class EvidenceChapterIdMissingError extends Error {
  constructor() {
    super("EVIDENCE_CHAPTER_ID_MISSING");
    this.name = "EvidenceChapterIdMissingError";
  }
}

/** Resolve real chapter id from API source — never use chapter_index as id. */
export function resolveEvidenceChapterId(source: EvidenceSourceDetail): number {
  const id = source.chapter_id;
  if (id == null || !Number.isFinite(Number(id)) || Number(id) <= 0) {
    throw new EvidenceChapterIdMissingError();
  }
  return Number(id);
}

function applyRestoreParams(
  params: URLSearchParams,
  restore?: WholeBookEvidenceRestoreState,
): void {
  if (!restore) return;
  if (restore.restoreFunction) params.set("restoreFunction", restore.restoreFunction);
  if (restore.restoreStatus) params.set("restoreStatus", restore.restoreStatus);
  if (restore.restoreCursor) params.set("restoreCursor", restore.restoreCursor);
  if (restore.restoreChapter) params.set("restoreChapter", restore.restoreChapter);
}

export function buildWholeBookEvidenceSearchParams(
  source: EvidenceSourceDetail,
  chapterId: number,
  options?: WholeBookEvidenceDeepLinkOptions,
): URLSearchParams {
  if (!Number.isFinite(chapterId) || chapterId <= 0) {
    throw new EvidenceChapterIdMissingError();
  }
  // Require real chapter_id from source — never invent from chapter_index.
  if (source.chapter_id == null || !Number.isFinite(Number(source.chapter_id)) || Number(source.chapter_id) <= 0) {
    throw new EvidenceChapterIdMissingError();
  }
  if (Number(source.chapter_id) !== Number(chapterId)) {
    throw new EvidenceChapterIdMissingError();
  }

  const params = new URLSearchParams();
  params.set("chapter", String(chapterId));
  params.set("paragraph", String(source.paragraph_index));
  params.set("view", "reading");
  params.set("evidenceId", String(source.evidence_id));
  params.set("chapterId", String(chapterId));
  params.set("paragraphIndex", String(source.paragraph_index));
  params.set("startOffset", String(source.start_offset));
  params.set("endOffset", String(source.end_offset));
  if (source.paragraph_text_hash) {
    params.set("paragraphContentHash", source.paragraph_text_hash);
  }
  if (source.snapshot_id != null) {
    params.set("snapshotId", String(source.snapshot_id));
  }
  // Explicit display order — never used as chapter id.
  if (source.chapter_index != null) {
    params.set("chapterIndex", String(source.chapter_index));
  }
  if (options?.returnModule) {
    params.set("returnTo", "whole-book");
    params.set("returnModule", options.returnModule);
  }
  applyRestoreParams(params, options?.restore);
  return params;
}

export function wholeBookEvidenceReaderHref(
  bookId: number,
  source: EvidenceSourceDetail,
  chapterId: number,
  options?: WholeBookEvidenceDeepLinkOptions,
): string {
  return `/books/${bookId}?${buildWholeBookEvidenceSearchParams(source, chapterId, options).toString()}`;
}

/** Navigate to reader; caller must validate source.state === "valid". */
export function openEvidenceInReader(
  bookId: number,
  source: EvidenceSourceDetail,
  chapterId: number,
  options?: WholeBookEvidenceDeepLinkOptions,
): string {
  if (source.state === "stale") {
    throw new Error("EVIDENCE_STALE");
  }
  if (source.state === "missing") {
    throw new Error("EVIDENCE_MISSING");
  }
  return wholeBookEvidenceReaderHref(bookId, source, chapterId, options);
}

/** Build reader href from source alone — uses real chapter_id only. */
export function openEvidenceInReaderFromSource(
  bookId: number,
  source: EvidenceSourceDetail,
  options?: WholeBookEvidenceDeepLinkOptions,
): string {
  const chapterId = resolveEvidenceChapterId(source);
  return openEvidenceInReader(bookId, source, chapterId, options);
}

export function wholeBookFreeModuleHref(
  bookId: number,
  moduleKey = "structure",
  restore?: WholeBookEvidenceRestoreState,
): string {
  const params = new URLSearchParams();
  params.set("module", moduleKey);
  applyRestoreParams(params, restore);
  if (restore?.restoreFunction) params.set("cfFunction", restore.restoreFunction);
  if (restore?.restoreStatus) params.set("cfStatus", restore.restoreStatus);
  if (restore?.restoreChapter) params.set("cfChapter", restore.restoreChapter);
  return `/books/${bookId}/whole-book?${params.toString()}`;
}

export function readEvidenceRestoreState(
  searchParams: URLSearchParams,
): WholeBookEvidenceRestoreState {
  return {
    restoreFunction: searchParams.get("restoreFunction"),
    restoreStatus: searchParams.get("restoreStatus"),
    restoreCursor: searchParams.get("restoreCursor"),
    restoreChapter: searchParams.get("restoreChapter") || searchParams.get("cfChapter"),
  };
}
