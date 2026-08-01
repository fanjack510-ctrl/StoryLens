/**
 * Evidence deep-link for Wave D Free whole-book product.
 * Reuses BookRoutePage reader with offset highlight query params.
 * No fuzzy fallback / no evidence_map wrapper.
 */
import type { EvidenceSourceDetail } from "./wholeBookFoundationApi";

export type WholeBookEvidenceReaderParams = {
  evidenceId: number;
  chapterId: number;
  paragraphIndex: number;
  startOffset: number;
  endOffset: number;
};

export type WholeBookEvidenceDeepLinkOptions = {
  /** Preserve Free module after returning from reader (e.g. structure). */
  returnModule?: string;
};

export function buildWholeBookEvidenceSearchParams(
  source: EvidenceSourceDetail,
  chapterId: number,
  options?: WholeBookEvidenceDeepLinkOptions,
): URLSearchParams {
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
  if (options?.returnModule) {
    params.set("returnTo", "whole-book");
    params.set("returnModule", options.returnModule);
  }
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

export function wholeBookFreeModuleHref(
  bookId: number,
  moduleKey = "structure",
): string {
  return `/books/${bookId}/whole-book?module=${encodeURIComponent(moduleKey)}`;
}
