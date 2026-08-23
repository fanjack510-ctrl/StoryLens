import { api } from "./apiClient";

/** 跨书检索：在所有分析过的书里找东西。
 *
 *  两层，可信度和覆盖面都不一样：
 *   · `search` 关键词——确定、即时、可核对，覆盖**全部**条目（含逐章钩子和原文证据）。免费。
 *   · `byMeaning` 按意思——一次模型判断，只覆盖**写法层**。Pro。
 *
 *  覆盖面的差别必须让用户看见：以为搜过了全部、其实只搜了写法层，
 *  「没找到」就会被读成「这些书里没有」——那是一个错的结论。
 */
export type SearchHit = {
  book_id: number;
  book_title: string;
  kind: string;
  kind_label: string;
  title: string;
  snippet: string;
  /** 第几章。写法层的条目大多没有章号，那时是 null——不是 0。 */
  chapter: number | null;
  matched: string[];
  score: number;
};

export type KeywordResult = {
  query: string;
  hits: SearchHit[];
  total: number;
  /** 截断了就要说。悄悄截断读起来和「一共就这么多」一模一样。 */
  truncated: boolean;
  searched_items: number;
  message: string;
};

export type MeaningMatch = {
  book_id: number;
  book_title: string;
  kind: string;
  kind_label: string;
  title: string;
  detail: string;
  chapter: number | null;
  /** 它为什么符合这个要求——不是复述它本身是什么。 */
  why: string;
};

export type MeaningResult = {
  query: string;
  matches: MeaningMatch[];
  dropped: string[];
  searched_craft_items: number;
  total_craft_items: number;
  truncated: boolean;
  scope_note: string;
  provider_name: string;
  model_name: string;
};

export type SearchScope = {
  book_count: number;
  books: Array<{ book_id: number; title: string }>;
  item_count: number;
  craft_count: number;
  kinds: Array<{ kind: string; label: string; count: number }>;
};

export const crossBookApi = {
  scope: () => api<SearchScope>("/api/v1/cross-book/scope"),

  search: (query: string, opts?: { kinds?: string[]; limit?: number }) =>
    api<KeywordResult>(
      `/api/v1/cross-book/search?q=${encodeURIComponent(query)}` +
        (opts?.kinds?.length ? `&kinds=${encodeURIComponent(opts.kinds.join(","))}` : "") +
        (opts?.limit ? `&limit=${opts.limit}` : ""),
    ),

  byMeaning: (query: string, bookIds?: number[]) =>
    api<MeaningResult>("/api/v1/cross-book/by-meaning", {
      method: "POST",
      body: JSON.stringify({ query, ...(bookIds?.length ? { book_ids: bookIds } : {}) }),
    }),
};
