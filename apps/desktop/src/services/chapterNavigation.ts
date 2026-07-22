/**
 * Unified chapter reading navigation helpers (long-book safe).
 * Ordinals are body-reading order, never raw database chapter ids.
 */

import type { Chapter } from "../types";

export const CHAPTER_RANGE_SIZE = 100;

export type ChapterRange = {
  startOrdinal: number;
  endOrdinal: number;
  label: string;
};

export type NavigateToChapterReadingOptions = {
  /** Scroll reading pane to top after navigation (caller applies). */
  scrollReadingTop?: boolean;
};

/** Body chapters only — front_matter / 资料 excluded from ordinals. */
export function bodyChapters(chapters: Chapter[] | null | undefined): Chapter[] {
  if (!chapters?.length) return [];
  return chapters.filter((c) => c.section_type === "chapter");
}

export function frontMatterChapters(chapters: Chapter[] | null | undefined): Chapter[] {
  if (!chapters?.length) return [];
  return chapters.filter((c) => c.section_type !== "chapter");
}

/** 1-based ordinal in body reading order. */
export function bodyOrdinalOf(
  chapters: Chapter[] | null | undefined,
  chapterId: number | null | undefined,
): number | null {
  if (!chapterId) return null;
  const body = bodyChapters(chapters);
  const idx = body.findIndex((c) => c.id === chapterId);
  return idx >= 0 ? idx + 1 : null;
}

export function chapterByBodyOrdinal(
  chapters: Chapter[] | null | undefined,
  ordinal: number,
): Chapter | null {
  const body = bodyChapters(chapters);
  if (!Number.isFinite(ordinal) || ordinal < 1 || ordinal > body.length) return null;
  return body[ordinal - 1] || null;
}

export function resolveOrdinalJump(
  chapters: Chapter[] | null | undefined,
  raw: string,
):
  | { ok: true; chapter: Chapter; ordinal: number }
  | { ok: false; reason: "invalid" | "out_of_range"; total: number } {
  const total = bodyChapters(chapters).length;
  const trimmed = raw.trim();
  if (!trimmed || !/^\d+$/.test(trimmed)) {
    return { ok: false, reason: "invalid", total };
  }
  const ordinal = Number(trimmed);
  if (!Number.isFinite(ordinal) || ordinal < 1) {
    return { ok: false, reason: "invalid", total };
  }
  if (ordinal > total) {
    return { ok: false, reason: "out_of_range", total };
  }
  const chapter = chapterByBodyOrdinal(chapters, ordinal);
  if (!chapter) return { ok: false, reason: "out_of_range", total };
  return { ok: true, chapter, ordinal };
}

export function buildChapterRanges(totalBodyChapters: number, size = CHAPTER_RANGE_SIZE): ChapterRange[] {
  if (totalBodyChapters <= 0) return [];
  const ranges: ChapterRange[] = [];
  for (let start = 1; start <= totalBodyChapters; start += size) {
    const end = Math.min(start + size - 1, totalBodyChapters);
    ranges.push({
      startOrdinal: start,
      endOrdinal: end,
      label: `${start}—${end}`,
    });
  }
  return ranges;
}

export function rangeContainingOrdinal(
  ranges: ChapterRange[],
  ordinal: number | null,
): ChapterRange | null {
  if (!ordinal || !ranges.length) return ranges[0] || null;
  return ranges.find((r) => ordinal >= r.startOrdinal && ordinal <= r.endOrdinal) || ranges[0];
}

export function chaptersInRange(
  chapters: Chapter[] | null | undefined,
  range: ChapterRange | null,
): Chapter[] {
  const body = bodyChapters(chapters);
  if (!range) return body;
  return body.slice(range.startOrdinal - 1, range.endOrdinal);
}

export function filterChaptersByTitle(
  chapters: Chapter[] | null | undefined,
  query: string,
): Chapter[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return bodyChapters(chapters).filter((c) => {
    const title = (c.display_title || c.title || "").toLowerCase();
    const num = String(c.chapter_number_normalized || c.chapter_index);
    const ordinal = String(bodyOrdinalOf(chapters, c.id) || "");
    return title.includes(q) || num.includes(q) || ordinal.includes(q);
  });
}

export function adjacentBodyChapters(
  chapters: Chapter[] | null | undefined,
  chapterId: number | null | undefined,
): { prev: Chapter | null; next: Chapter | null; ordinal: number | null } {
  const body = bodyChapters(chapters);
  const idx = body.findIndex((c) => c.id === chapterId);
  if (idx < 0) return { prev: null, next: null, ordinal: null };
  return {
    prev: idx > 0 ? body[idx - 1] : null,
    next: idx < body.length - 1 ? body[idx + 1] : null,
    ordinal: idx + 1,
  };
}

export function chapterListLabel(c: Chapter, ordinal?: number | null): string {
  if (c.section_type !== "chapter") return "资料";
  const n = ordinal ?? c.chapter_number_normalized ?? c.chapter_index;
  return String(n);
}

/**
 * Build reading search params: real chapter id + view=reading.
 * Clears analysisRun / tab / journeyView / resultTab / mode / scene.
 */
export function buildChapterReadingSearchParams(chapterId: number): URLSearchParams {
  const next = new URLSearchParams();
  next.set("chapter", String(chapterId));
  next.set("view", "reading");
  return next;
}

export function applyNavigateToChapterReading(
  setSearchParams: (
    next: URLSearchParams | ((prev: URLSearchParams) => URLSearchParams),
    opts?: { replace?: boolean },
  ) => void,
  chapterId: number,
  options?: { replace?: boolean },
): void {
  setSearchParams(buildChapterReadingSearchParams(chapterId), {
    replace: options?.replace ?? false,
  });
}

export function scrollReadingPaneToTop(): void {
  const pane =
    document.querySelector<HTMLElement>(".workspace-reader") ||
    document.querySelector<HTMLElement>(".book-shell-simplified .reader") ||
    document.querySelector<HTMLElement>(".workspace-reading-canvas");
  if (pane) {
    pane.scrollTop = 0;
  }
  try {
    if (typeof window.scrollTo === "function") {
      window.scrollTo(0, 0);
    }
  } catch {
    // jsdom may not implement scrollTo
  }
}
