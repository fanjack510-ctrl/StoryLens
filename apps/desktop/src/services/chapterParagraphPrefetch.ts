/**
 * Chapter paragraph prefetch — adjacent / hover only, never whole book.
 */

import type { QueryClient } from "@tanstack/react-query";
import { booksApi } from "./booksApi";

const PREFETCH_STALE_MS = 60_000;
const MAX_CONCURRENT = 2;

let inFlight = 0;
const queue: Array<() => void> = [];
const scheduled = new Set<number>();

function pump(): void {
  while (inFlight < MAX_CONCURRENT && queue.length) {
    const next = queue.shift();
    if (next) next();
  }
}

export function chapterParagraphsQueryKey(chapterId: number, offset = 0) {
  return ["paragraphs", chapterId, offset] as const;
}

/** Prefetch one chapter body with concurrency limit and dedupe. */
export function prefetchChapterParagraphs(
  queryClient: QueryClient,
  chapterId: number | null | undefined,
): void {
  if (!chapterId || !Number.isFinite(chapterId) || chapterId <= 0) return;
  if (scheduled.has(chapterId)) return;
  const existing = queryClient.getQueryData(chapterParagraphsQueryKey(chapterId, 0));
  if (existing) return;

  scheduled.add(chapterId);
  const run = () => {
    inFlight += 1;
    void queryClient
      .prefetchQuery({
        queryKey: chapterParagraphsQueryKey(chapterId, 0),
        queryFn: () => booksApi.paragraphs(chapterId, 0, 200),
        staleTime: PREFETCH_STALE_MS,
      })
      .catch(() => undefined)
      .finally(() => {
        inFlight -= 1;
        scheduled.delete(chapterId);
        pump();
      });
  };

  if (inFlight >= MAX_CONCURRENT) {
    queue.push(run);
  } else {
    run();
  }
}

export function prefetchAdjacentChapterParagraphs(
  queryClient: QueryClient,
  prevId: number | null | undefined,
  nextId: number | null | undefined,
): void {
  const idle =
    typeof window !== "undefined" && typeof window.requestIdleCallback === "function"
      ? window.requestIdleCallback.bind(window)
      : (cb: () => void) => window.setTimeout(cb, 0);
  idle(() => {
    prefetchChapterParagraphs(queryClient, prevId);
    prefetchChapterParagraphs(queryClient, nextId);
  });
}

/** Test helpers */
export function __resetChapterPrefetchStateForTests(): void {
  inFlight = 0;
  queue.length = 0;
  scheduled.clear();
}
