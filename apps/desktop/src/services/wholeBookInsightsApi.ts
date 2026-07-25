import { api } from "./apiClient";

export type WholeBookInsightsDeepLink = {
  chapter_id: number;
  scene_id?: number | null;
  paragraph_id?: string | null;
  chapter_level?: boolean;
};

export type WholeBookInsightsSceneRow = {
  scene_id: number;
  scene_ordinal: number;
  tension_score: number;
  hook_score: number;
  payoff_score: number;
  hooks: unknown[];
  payoffs: unknown[];
  risk_points: unknown[];
  evidence_paragraph_ids: string[];
  function_tags: string[];
  deep_link: WholeBookInsightsDeepLink;
};

export type WholeBookInsightsChapterRow = {
  chapter_id: number;
  chapter_index: number;
  chapter_title: string;
  display_title: string;
  analysis_run_id: number | null;
  effective_status: string | null;
  completed_at: string | null;
  is_valid: boolean;
  scenes: WholeBookInsightsSceneRow[];
};

export type WholeBookInsightsResult = {
  schema: string;
  book_id: number;
  coverage: {
    total_chapters: number;
    valid_chapters: number;
    invalid_chapters: number;
  };
  journey_curve: Array<{
    chapter_index: number;
    tension: number;
    hook: number;
    payoff: number;
  }>;
  pacing?: { summary?: string };
  peaks?: unknown[];
  valleys?: unknown[];
  hooks?: unknown[];
  payoffs?: unknown[];
  functions?: unknown[];
  diagnostics?: unknown[];
  chapters?: WholeBookInsightsChapterRow[];
  data_source?: {
    capability_key?: string;
    api_alias?: string;
    coverage?: WholeBookInsightsResult["coverage"];
  };
  computed_at?: string;
};

export const wholeBookInsightsApi = {
  fetch: (bookId: number) =>
    api<WholeBookInsightsResult>(`/api/v1/books/${bookId}/pro/whole-book-insights`),
};
