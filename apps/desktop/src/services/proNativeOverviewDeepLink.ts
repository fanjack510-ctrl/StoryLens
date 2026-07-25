/**
 * Evidence deep-link for Pro Native Overview — reuses BookRoutePage reader params.
 * Pattern: /books/{bookId}?chapter=&paragraph=&view=reading (+ optional hash).
 */
import type { EvidenceDeepLink, EvidenceIndexEntry } from "./proNativeOverviewApi";

export function buildOverviewEvidenceSearchParams(
  deepLink: EvidenceDeepLink,
): URLSearchParams {
  const params = new URLSearchParams();
  params.set("chapter", String(deepLink.chapter_id));
  params.set("paragraph", deepLink.paragraph_id);
  params.set("view", "reading");
  if (deepLink.content_hash) {
    params.set("paragraphContentHash", deepLink.content_hash);
  }
  return params;
}

export function overviewEvidenceHref(bookId: number, deepLink: EvidenceDeepLink): string {
  return `/books/${bookId}?${buildOverviewEvidenceSearchParams(deepLink).toString()}`;
}

export function resolveEvidenceEntry(
  evidenceIndex: EvidenceIndexEntry[] | undefined,
  evidenceId: string,
): EvidenceIndexEntry | null {
  if (!evidenceIndex?.length) return null;
  return evidenceIndex.find((entry) => entry.evidence_id === evidenceId) ?? null;
}

export function firstEvidenceHref(
  bookId: number,
  evidenceRefs: string[] | undefined,
  evidenceIndex: EvidenceIndexEntry[] | undefined,
): string | null {
  if (!evidenceRefs?.length) return null;
  for (const ref of evidenceRefs) {
    const entry = resolveEvidenceEntry(evidenceIndex, ref);
    if (entry?.deep_link?.paragraph_id && entry.deep_link.chapter_id) {
      return overviewEvidenceHref(bookId, entry.deep_link);
    }
  }
  return null;
}
