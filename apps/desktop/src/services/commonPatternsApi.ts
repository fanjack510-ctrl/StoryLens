import { api } from "./apiClient";

/** 共性视图：把一组书摆在一起，看它们共同做对了什么。
 *
 *  分两层，是因为两层的可信度不一样：
 *   · overview 是**数出来的**——类型分布、每本读到第几章。任何时候都成立，免费。
 *   · patterns 是**归纳出来的**——需要被检验，所以每条都带着它引用的书和技法名。
 *  把两者放在同一个界面里但标明来源，读的人才知道哪一半可以直接信。
 */
export type PatternBook = {
  book_id: number;
  title: string;
  usable: boolean;
  /** 这本书为什么进不了比较。空字符串＝进得来。 */
  excluded_reason: string;
  primary_genre: string;
  chapters_analysed: number;
  chapters_total: number;
  scope_kind: "full" | "opening";
  /** 后端算好的一句话：「开篇 5 章 / 全书 542 章」。 */
  scope_label: string;
  technique_count: number;
  hook_count: number;
  /** 章末钩子密度。原始计数在书长差异面前没有可比性。 */
  hooks_per_chapter: number | null;
  standout_moment_count: number;
};

export type PatternInstance = {
  book_id: number;
  book_title: string;
  technique_name: string;
  how_this_book_does_it: string;
};

export type CommonPattern = {
  name: string;
  what_they_do: string;
  why_it_works: string;
  book_count: number;
  instances: PatternInstance[];
};

export type PatternsOverview = {
  books: PatternBook[];
  usable_count: number;
  total_count: number;
  genres: Array<{ genre: string; count: number }>;
  technique_total: number;
  opening_only_count: number;
  /** 有的书只拆了开篇、有的拆了整本。混着比不是错，但读结论的人得知道自己在比什么。 */
  mixed_scope: boolean;
  can_synthesize: boolean;
  min_books: number;
  blocked_reason: string;
};

export type PatternsResult = PatternsOverview & {
  patterns: CommonPattern[];
  not_shared: Array<{ book_id: number; book_title: string; what_only_this_one_does: string }>;
  provider_name: string;
  model_name: string;
};

export const commonPatternsApi = {
  overview: (collectionId: number) =>
    api<PatternsOverview>(`/api/v1/collections/${collectionId}/common-patterns/overview`),

  synthesize: (collectionId: number) =>
    api<PatternsResult>(`/api/v1/collections/${collectionId}/common-patterns`, {
      method: "POST",
    }),
};
