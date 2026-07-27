import type { PatternMapEvidenceRefDto } from "../contracts/patternMap.draft";

/**
 * Build workspace search params to locate evidence text.
 * Reuses existing Reader Journey / reading deep-link conventions:
 *   chapter + scene + paragraph (+ optional view).
 *
 * paragraphContentHash is carried for future snapshot integrity checks;
 * current production reader does not yet validate hash on scroll.
 */
export function buildEvidenceDeepLinkParams(
  ref: PatternMapEvidenceRefDto,
  options?: { view?: "reading" | "journey"; bookSnapshotId?: string },
): URLSearchParams {
  const params = new URLSearchParams();
  params.set("chapter", String(ref.chapterId));
  if (ref.sceneId != null) {
    params.set("scene", String(ref.sceneId));
  }
  params.set("paragraph", ref.paragraphId);
  params.set("view", options?.view ?? "reading");
  if (options?.bookSnapshotId ?? ref.bookSnapshotId) {
    params.set("bookSnapshotId", options?.bookSnapshotId ?? ref.bookSnapshotId);
  }
  params.set("paragraphContentHash", ref.paragraphContentHash);
  return params;
}

export function evidenceDeepLinkHref(
  bookId: number,
  ref: PatternMapEvidenceRefDto,
  options?: { view?: "reading" | "journey" },
): string {
  const params = buildEvidenceDeepLinkParams(ref, options);
  return `/books/${bookId}?${params.toString()}`;
}

export type EvidenceLocateCapability = {
  canJumpChapter: boolean;
  canJumpScene: boolean;
  canJumpParagraph: boolean;
  canValidateContentHash: boolean;
  notes: string[];
};

/** Audit result for Integration — what production already supports today. */
export const CURRENT_EVIDENCE_LOCATE_CAPABILITY: EvidenceLocateCapability = {
  canJumpChapter: true,
  canJumpScene: true,
  canJumpParagraph: true,
  canValidateContentHash: false,
  notes: [
    "chapterNavigation + BookRoutePage already deep-link chapter via ?chapter=",
    "Reader Journey selection transaction already uses ?scene= and ?paragraph=",
    "StructuredChapterTextPane scrolls to #sync-p-{paragraphId}",
    "paragraphContentHash validation requires Agent A snapshot integrity wiring — not yet in UI",
  ],
};
