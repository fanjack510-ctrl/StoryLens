import { api } from "./apiClient";
import type { LibraryItem } from "./booksApi";

/** 书单：一组可以被反复回到的书。
 *
 *  扫榜的做法是「一次过十几本新书，看它们怎么开头」，然后横着比。那批书需要一个名字才能被
 *  反复回到——否则每次都要在书库里重新挑一遍，而「上次那批」这句话根本无法表达。
 *
 *  书单本身免费：它不调用模型，是个文件夹。付费的是**在一组书上做的事**（共性视图、
 *  跨书检索），那些各自把自己的门。
 */
export type Collection = {
  id: number;
  name: string;
  /** 建这个书单是为了看什么。几周后回来时，这句话是唯一能说明当初标准的东西。 */
  note: string;
  book_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type CollectionDetail = Collection & {
  /** 和书库用的是同一种卡片——同样的类型标、同样的分析状态。 */
  books: LibraryItem[];
};

export const collectionsApi = {
  list: () => api<{ items: Collection[] }>("/api/v1/collections").then((r) => r.items),

  read: (id: number) => api<CollectionDetail>(`/api/v1/collections/${id}`),

  create: (body: { name: string; note?: string }) =>
    api<Collection>("/api/v1/collections", {
      method: "POST",
      body: JSON.stringify({ name: body.name, note: body.note ?? "" }),
    }),

  update: (id: number, body: { name?: string; note?: string }) =>
    api<Collection>(`/api/v1/collections/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  remove: (id: number) =>
    api<{ deleted: boolean }>(`/api/v1/collections/${id}`, { method: "DELETE" }),

  /** 已经在里面的书会被跳过，不算错误——挑着挑着忘了加过没有是常规动作。 */
  addBooks: (id: number, bookIds: number[]) =>
    api<{ added: number; book_count: number }>(`/api/v1/collections/${id}/books`, {
      method: "POST",
      body: JSON.stringify({ book_ids: bookIds }),
    }),

  removeBook: (id: number, bookId: number) =>
    api<{ book_count: number }>(`/api/v1/collections/${id}/books/${bookId}`, {
      method: "DELETE",
    }),
};
