import { api } from "../../services/apiClient";

/**
 * The book profile — what kind of novel this is, decided before anything expensive reads it.
 *
 * The five axes are closed sets and the backend owns the vocabulary: it sends the options
 * the dropdowns render, and the list of extraction deltas a given set of answers switches
 * on. Nothing here re-derives either. The same rule kept in two places drifts, and this
 * codebase has already paid for that once with two copies of the analysis prompts.
 */

export type ProfileStatus = "draft" | "confirmed";

/** Where a value came from. `user` outranks every inference, including the whole-book one. */
export type AxisSource = "L0-A" | "L0-B" | "L0-C" | "user" | "";

export interface ProfileAxis {
  value: string;
  source: AxisSource;
  /** Paragraph anchors for a sampled read, or the counted figures behind a statistic. */
  evidence?: unknown;
  confidence?: number;
}

/** Where the counted half and the sampled read disagreed, and which one was kept. */
export interface ProfileDisagreement {
  axis: string;
  counted: string;
  read: string;
  kept: string;
}

export interface ProfileOption {
  axis: string;
  options: Array<{ value: string; label: string }>;
}

export interface ProfileStatistics {
  chapters: number;
  total_chars: number;
  chapter_chars_median: number;
  chapter_chars_p10: number;
  chapter_chars_p90: number;
  paragraphs_per_chapter_median: number;
  dialogue_ratio: number;
  vocabulary_per_10k: Record<string, number>;
}

export interface BookProfile {
  book_id: number;
  status: ProfileStatus;
  axes: Record<string, ProfileAxis>;
  disagreements: ProfileDisagreement[];
  statistics: ProfileStatistics;
  /** Per-name mention counts across ten equal slices of the book. */
  name_deciles: Record<string, number[]>;
  candidate_names: string[];
  sample_chapters: number[];
  options: ProfileOption[];
  active_deltas: string[];
}

export const AXIS_ORDER = ["monetization", "audience", "engine", "pov", "length"] as const;

export const AXIS_NAMES: Record<string, string> = {
  monetization: "变现模式",
  audience: "情感主轴",
  engine: "驱动引擎",
  pov: "视角结构",
  length: "篇幅",
};

export const SOURCE_NAMES: Record<string, string> = {
  "L0-A": "全书计数",
  "L0-C": "全书计数",
  "L0-B": "采样判读",
  user: "你的选择",
};

export async function getBookProfile(bookId: number): Promise<BookProfile | null> {
  try {
    return await api<BookProfile>(`/api/v1/books/${bookId}/profile`);
  } catch {
    // A book that has never been profiled is the normal first state, not an error worth
    // showing — the caller drafts one.
    return null;
  }
}

/** Counts the whole text. Free, no provider call, so it is safe to trigger from a page load. */
export async function draftBookProfile(bookId: number): Promise<BookProfile> {
  return api<BookProfile>(`/api/v1/books/${bookId}/profile/draft`, { method: "POST" });
}

export async function confirmBookProfile(
  bookId: number,
  axes: Record<string, string>,
): Promise<BookProfile> {
  return api<BookProfile>(`/api/v1/books/${bookId}/profile/confirm`, {
    method: "POST",
    body: JSON.stringify({ axes }),
  });
}

export async function resetBookProfile(bookId: number): Promise<void> {
  await api(`/api/v1/books/${bookId}/profile/reset`, { method: "POST" });
}
