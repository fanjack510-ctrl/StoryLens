import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import {
  __resetChapterPrefetchStateForTests,
  chapterParagraphsQueryKey,
  prefetchChapterParagraphs,
} from "./chapterParagraphPrefetch";
import { booksApi } from "./booksApi";

vi.mock("./booksApi", () => ({
  booksApi: {
    paragraphs: vi.fn(),
  },
}));

describe("chapterParagraphPrefetch", () => {
  beforeEach(() => {
    __resetChapterPrefetchStateForTests();
    vi.mocked(booksApi.paragraphs).mockResolvedValue({
      items: [{ id: "p1", raw_text: "x" }],
      offset: 0,
      limit: 200,
      total: 1,
      has_more: false,
    } as never);
  });

  afterEach(() => {
    __resetChapterPrefetchStateForTests();
    vi.clearAllMocks();
  });

  it("dedupes repeated prefetch for the same chapter", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    prefetchChapterParagraphs(client, 7);
    prefetchChapterParagraphs(client, 7);
    prefetchChapterParagraphs(client, 7);
    await vi.waitFor(() => {
      expect(booksApi.paragraphs).toHaveBeenCalledTimes(1);
      expect(client.getQueryState(chapterParagraphsQueryKey(7, 0))?.status).toBe(
        "success",
      );
    });
    expect(booksApi.paragraphs).toHaveBeenCalledWith(7, 0, 200);
  });

  it("skips prefetch when cache already has data", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(chapterParagraphsQueryKey(3, 0), { items: [] });
    prefetchChapterParagraphs(client, 3);
    await Promise.resolve();
    expect(booksApi.paragraphs).not.toHaveBeenCalled();
  });
});
