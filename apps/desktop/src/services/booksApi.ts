import { api } from "./apiClient";
import type { Book, Chapter, ImportDiagnostics, ParagraphPage } from "../types";
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
  preview: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return api<ImportDiagnostics>("/api/v1/books/chapter-detection/preview", {
      method: "POST",
      body: data,
    });
  },
  importFile: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return api<{ book_id: number }>("/api/v1/books/import", {
      method: "POST",
      body: data,
    });
  },
};
