import type { Chapter, Run } from "../types";

export type ChapterAnalysisBadge =
  | "unanalyzed"
  | "analyzing"
  | "scene_ready"
  | "journey_ready";

const PROCESSING = new Set([
  "queued",
  "running",
  "boundary_candidates_running",
  "boundary_confirmed",
  "scene_analysis_running",
  "reader_journey_processing",
  "reader_journey_running",
  "reader_journey_scene_profiles_running",
  "reader_journey_chapter_running",
]);

function newest(runs: Run[]): Run | null {
  if (!runs.length) return null;
  return runs.reduce((a, b) => (a.id >= b.id ? a : b));
}

/** Status hint for book-home chapter list — never auto-navigates. */
export function chapterAnalysisBadge(
  chapterId: number,
  runs: Run[] | null | undefined,
): ChapterAnalysisBadge {
  const chapterRuns = (runs || []).filter((r) => String(r.subject_id) === String(chapterId));
  const run = newest(chapterRuns);
  if (!run) return "unanalyzed";
  if (PROCESSING.has(run.status)) return "analyzing";
  if (run.status === "succeeded" && run.chapter_complete === true) return "journey_ready";
  if (run.status === "succeeded") return "scene_ready";
  return "unanalyzed";
}

export function chapterAnalysisBadgeLabel(badge: ChapterAnalysisBadge): string {
  switch (badge) {
    case "analyzing":
      return "分析中";
    case "scene_ready":
      return "已有场景分析";
    case "journey_ready":
      return "已有阅读旅程";
    default:
      return "未分析";
  }
}

export function isBookHomePath(search: URLSearchParams | { get: (k: string) => string | null }): boolean {
  return !search.get("chapter");
}

export type BookHomeChapterRow = {
  id: number;
  title: string;
  numLabel: string;
  badge: ChapterAnalysisBadge;
  badgeLabel: string;
};

export function buildBookHomeChapterRows(
  chapters: Chapter[] | null | undefined,
  runs: Run[] | null | undefined,
): BookHomeChapterRow[] {
  return (chapters || []).map((c) => {
    const badge = chapterAnalysisBadge(c.id, runs);
    const title = c.display_title || c.title;
    const numLabel =
      c.section_type === "front_matter"
        ? "资料"
        : String(c.chapter_number_normalized || c.chapter_index).padStart(2, "0");
    return {
      id: c.id,
      title,
      numLabel,
      badge,
      badgeLabel: chapterAnalysisBadgeLabel(badge),
    };
  });
}
