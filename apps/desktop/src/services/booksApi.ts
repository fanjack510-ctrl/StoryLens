import { api } from "./apiClient";
import type { Book, Chapter, ImportDiagnostics, ParagraphPage } from "../types";
export type MaterialKind = "fiction" | "reference";

/** 书库列表里的一本书。文案由后端定，客户端照着渲染。 */
export type LibraryItem = {
  id: number;
  title: string;
  /** 与书名不同时才有值——同名时重复显示等于同一句话说两遍。 */
  source_file_name: string;
  format: string;
  created_at: string | null;
  material_kind: MaterialKind;
  /** false = 程序推的，界面要标「待确认」。 */
  material_kind_confirmed: boolean;
  kind_label: string;
  chapter_count: number;
  analysis_state: "idle" | "running" | "done";
  analysis_state_label: string;
  /** 最后一次分析的时间；没跑过则是导入时间。首页按它排序。 */
  last_activity_at: string | null;
};

export const booksApi = {
  list: () => api<Book[]>("/api/v1/books"),
  detail: (id: number) => api<Book>(`/api/v1/books/${id}`),
  chapters: (id: number) => api<Chapter[]>(`/api/v1/books/${id}/chapters`),
  paragraphs: (id: number, offset = 0, limit = 200, paragraphId?: string) =>
    api<ParagraphPage>(
      `/api/v1/chapters/${id}/paragraphs?offset=${offset}&limit=${limit}${paragraphId ? `&paragraph_id=${encodeURIComponent(paragraphId)}` : ""}`,
    ),
  diagnostics: (id: number) =>
    api<ImportDiagnostics>(`/api/v1/books/${id}/import-diagnostics`),
  reparsePreview: (id: number) =>
    api<ImportDiagnostics>(`/api/v1/books/${id}/reparse-preview`, {
      method: "POST",
    }),
  reparse: (id: number) =>
    api<ImportDiagnostics>(`/api/v1/books/${id}/reparse`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    }),
  reparseWithFilePreview: (id: number, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return api<any>(`/api/v1/books/${id}/reparse-with-file-preview`, {
      method: "POST",
      body: data,
    });
  },
  reparseWithFile: (
    id: number,
    file: File,
    strategy: string,
    confirmDifferent = false,
  ) => {
    const data = new FormData();
    data.append("file", file);
    data.append("confirm", "true");
    data.append("strategy", strategy);
    data.append("confirm_different_file", String(confirmDifferent));
    return api<any>(`/api/v1/books/${id}/reparse-with-file`, {
      method: "POST",
      body: data,
    });
  },
  /** 书库列表：类型、章节数、分析状态都由后端算好（INV-P4）。 */
  library: () => api<LibraryItem[]>("/api/v1/books/library"),
  setMaterialKind: (bookId: number, materialKind: "fiction" | "reference") =>
    api<{ book_id: number; material_kind: string }>(`/api/v1/books/${bookId}/material-kind`, {
      method: "PUT",
      body: JSON.stringify({ material_kind: materialKind }),
    }),
  preview: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return api<ImportDiagnostics>("/api/v1/books/chapter-detection/preview", {
      method: "POST",
      body: data,
    });
  },
  /** `analysisForm` is the reader's own answer from the import panel — "short" or "long".
   *  Omitted means nobody was asked and the length inference stands in. */
  importFile: (
    file: File,
    analysisForm?: "short" | "long",
    /** 「这是什么书」——小说还是工具书。它决定这本书能用哪几种读法。 */
    materialKind?: "fiction" | "reference",
  ) => {
    const data = new FormData();
    data.append("file", file);
    if (analysisForm) data.append("analysis_form", analysisForm);
    if (materialKind) data.append("material_kind", materialKind);
    return api<{ book_id: number }>("/api/v1/books/import", {
      method: "POST",
      body: data,
    });
  },
  delete: (id: number) =>
    api<void>(`/api/v1/books/${id}`, {
      method: "DELETE",
    }),
};
