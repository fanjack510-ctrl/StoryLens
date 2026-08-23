import { api } from "./apiClient";

/** 素材库：本地确定性引擎，把一本书拆成可复用的创作资料。
 *
 *  与产品其余部分的根本差别：不调云端模型、不要密钥、不花钱。
 *  跑一遍是同步的（整本书秒级到半分钟），所以 run 没有任务轮询——
 *  等响应回来就是结果。
 */

export type MaterialLabGenre = {
  slug: string;
  label: string;
  category_count: number;
};

export type GenreSuggestion = {
  genre_slug: string;
  label: string;
  /** 0 = 判不出来（run 时必须显式选类型）。 */
  confidence: number;
};

export type MaterialLabRunResult = {
  run_id: number;
  book_id: number;
  genre_slug: string;
  genre_source: "user" | "auto";
  genre_confidence: number;
  chapters: number;
  scenes: number;
  duplicate_chapters: number;
  skipped_short_scenes: number;
  materials: number;
};

export type MaterialLabRunInfo = {
  run_id: number;
  status: string;
  genre_slug: string;
  genre_source: string;
  genre_confidence: number;
  chapters: number;
  scenes: number;
  materials: number;
  created_at: string | null;
  finished_at: string | null;
};

export type MaterialLabSummary = {
  book_id: number;
  material_count: number;
  by_type: Record<string, number>;
  by_category: Array<{ key: string; label: string; count: number }>;
  last_run: MaterialLabRunInfo | null;
};

export type MaterialItem = {
  id: number;
  book_id: number;
  chapter_id: number;
  scene_seq: number;
  place: string;
  time_cue: string;
  genre_slug: string;
  material_type: string;
  category_key: string;
  category_label: string;
  subcategory_key: string;
  subcategory_label: string;
  title: string;
  /** 由槽位重组的可发表示例——从不拼接原文，这是引擎的核心承诺。 */
  concise_example: string;
  core_pattern: string;
  mechanism: string;
  suspense_question: string;
  applicable_stage: string;
  applicable_scene: string;
  emotion: string;
  tags: string[];
  quality_score: number;
  confidence: number;
  pattern_id: number | null;
  is_primary_variant: boolean;
};

export type MaterialListResult = { total: number; items: MaterialItem[] };

export type MaterialPattern = {
  id: number;
  genre_slug: string;
  category_key: string;
  category_label: string;
  core_pattern: string;
  mechanism: string;
  variant_count: number;
  book_count: number;
};

export type PatternListResult = { total: number; items: MaterialPattern[] };

export type MaterialFilters = {
  book_id?: number;
  material_type?: string;
  category_key?: string;
  min_score?: number;
  primary_only?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
};

function query(params: Record<string, unknown>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export const materialLabApi = {
  genres: () => api<{ items: MaterialLabGenre[] }>("/api/v1/material-lab/genres"),

  genreSuggestion: (bookId: number) =>
    api<GenreSuggestion>(`/api/v1/material-lab/books/${bookId}/genre-suggestion`),

  run: (bookId: number, genreSlug?: string) =>
    api<MaterialLabRunResult>(`/api/v1/material-lab/books/${bookId}/run`, {
      method: "POST",
      body: JSON.stringify({ genre_slug: genreSlug || null }),
    }),

  summary: (bookId: number) =>
    api<MaterialLabSummary>(`/api/v1/material-lab/books/${bookId}/summary`),

  materials: (filters: MaterialFilters) =>
    api<MaterialListResult>(`/api/v1/material-lab/materials${query(filters)}`),

  patterns: (params: { genre_slug?: string; category_key?: string; limit?: number }) =>
    api<PatternListResult>(`/api/v1/material-lab/patterns${query(params)}`),
};
