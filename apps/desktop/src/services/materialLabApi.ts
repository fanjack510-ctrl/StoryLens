import { api } from "./apiClient";

/** 题材知识库：只从已经完成全文拆文的小说中提取可核对素材。
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
  source_material_kind: "fiction" | "reference";
  source_material_kind_confirmed: boolean;
  knowledge_role: "genre_example" | "domain_reference";
  material_count: number;
  by_type: Record<string, number>;
  by_category: Array<{ key: string; label: string; count: number }>;
  last_run: MaterialLabRunInfo | null;
};

export type KnowledgeLibrarySummary = {
  knowledge_count: number;
  extracted_knowledge_count: number;
  imported_knowledge_count: number;
  source_book_count: number;
  legacy_source_book_count: number;
  by_role: { genre_example: number; domain_reference: number };
  by_genre: Array<{ slug: string; label: string; count: number }>;
  by_category: Array<{ key: string; label: string; count: number }>;
  taxonomy: Array<{
    slug: string;
    label: string;
    count: number;
    categories: Array<{ key: string; label: string; count: number }>;
  }>;
  sources: Array<{
    book_id: number;
    book_title: string;
    source_material_kind: "fiction" | "reference";
    source_material_kind_confirmed: boolean;
    knowledge_role: "genre_example" | "domain_reference";
    knowledge_count: number;
  }>;
};

export type KnowledgeSource = {
  book_id: number;
  book_title: string;
  breakdown_run_id: number;
  breakdown_completed_at: string | null;
  material_count: number;
  genre_slug: string;
  extracted: boolean;
};

export type KnowledgeSourceList = { total: number; items: KnowledgeSource[] };

export type MaterialItem = {
  id: number | string;
  origin: "whole_book" | "legacy_import" | "reference_corpus";
  book_id: number | null;
  source_book_title: string;
  chapter_id: number | null;
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
  /** 原书中支撑该知识条目的短摘录，以及可精确核对的真实段落 ID。 */
  source_excerpt: string;
  source_paragraph_ids: string[];
  source_material_kind: "fiction" | "reference";
  source_material_kind_confirmed: boolean;
  knowledge_role: "genre_example" | "domain_reference";
  knowledge_role_label: string;
  verification_label: string;
  /** 与分类命中位置一致的本地原文证据句，用于核对而非对外发布。 */
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
  pattern_id: number | string | null;
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

export type BookSkillArtifact = {
  schema_version: "storylens-book-skill/1.0";
  filename: string;
  skill_name: string;
  book_id: number;
  source_run_id: number;
  source_title: string;
  content: string;
  sections: string[];
};

export type MaterialFilters = {
  book_id?: number;
  genre_slug?: string;
  knowledge_role?: "genre_example" | "domain_reference";
  material_type?: string;
  category_key?: string;
  min_score?: number;
  primary_only?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
  source_kind?: "whole_book" | "legacy_import";
};

export type LegacyLibraryInspection = {
  compatible: true;
  source_name: string;
  source_size: number;
  fingerprint: string;
  book_count: number;
  material_count: number;
  primary_material_count: number;
  pattern_count: number;
  genre_count: number;
  category_count: number;
  subcategory_count: number;
  by_genre: Array<{ key: string; label: string; count: number }>;
  by_type: Array<{ key: string; label: string; count: number }>;
  contains_source_text: false;
};

export type LegacyImportStatus = {
  imported: boolean;
  batch_id: number | null;
  status: string;
  source_name: string;
  fingerprint: string;
  source_material_count: number;
  imported_count: number;
  primary_material_count: number;
  imported_at: string | null;
  contains_source_text: false;
  already_imported: boolean;
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
    api<MaterialLabSummary>(`/api/v1/material-lab/books/${bookId}/summary?view=knowledge-v1`),

  librarySummary: () =>
    api<KnowledgeLibrarySummary>("/api/v1/material-lab/library/summary"),

  librarySources: () =>
    api<KnowledgeSourceList>("/api/v1/material-lab/library/sources"),

  legacyImportStatus: () =>
    api<LegacyImportStatus>("/api/v1/material-lab/library/legacy/status"),

  inspectLegacyLibrary: (path: string) =>
    api<LegacyLibraryInspection>("/api/v1/material-lab/library/legacy/inspect", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  importLegacyLibrary: (path: string, expectedFingerprint: string) =>
    api<LegacyImportStatus>("/api/v1/material-lab/library/legacy/import", {
      method: "POST",
      body: JSON.stringify({
        path,
        expected_fingerprint: expectedFingerprint,
        confirm: true,
      }),
    }),

  extractLibrarySource: (bookId: number, genreSlug?: string) =>
    api<MaterialLabRunResult>(`/api/v1/material-lab/library/sources/${bookId}/extract`, {
      method: "POST",
      body: JSON.stringify({ genre_slug: genreSlug || null }),
    }),

  generateBookSkill: (bookId: number) =>
    api<BookSkillArtifact>(`/api/v1/material-lab/library/skills/${bookId}`, {
      method: "POST",
    }),

  materials: (filters: MaterialFilters) =>
    api<MaterialListResult>(
      `/api/v1/material-lab/materials${query({ ...filters, view: "knowledge-v1" })}`,
    ),

  patterns: (params: { genre_slug?: string; category_key?: string; limit?: number }) =>
    api<PatternListResult>(`/api/v1/material-lab/patterns${query(params)}`),
};
