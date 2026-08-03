/**
 * Free product Chapter Functions module container (CHG-20260803-042).
 * Owns pagination / filter / detail fetch against product APIs.
 * Panel remains presentational.
 */
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../../../services/apiClient";
import { wholeBookFreeProductApi } from "../../../services/wholeBookFreeProductApi";
import {
  deriveChapterFunctionsViewState,
  type ChapterFunctionItemV2,
  type ChapterFunctionsClientViewState,
  type ChapterFunctionsProductResponse,
} from "../../../services/chapterFunctionsResultV2";
import { ChapterFunctionsPanel } from "./ChapterFunctionsPanel";
import type { ChapterFunctionsFilters } from "./ChapterFunctionsPanel";

const EMPTY_FILTERS: ChapterFunctionsFilters = { function: "", status: "" };
const PAGE_LIMIT = 50;

export function ChapterFunctionsFreeModule({
  runId,
  runStatus,
  pageMode,
  onOpenEvidence,
  onRetry,
  onBack,
}: {
  runId: number | null;
  runStatus: string | null | undefined;
  pageMode: string;
  onOpenEvidence: (evidenceId: number) => void;
  onRetry?: () => void;
  onBack?: () => void;
}) {
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<ChapterFunctionsFilters>({
    function: params.get("cfFunction") || params.get("restoreFunction") || "",
    status: params.get("cfStatus") || params.get("restoreStatus") || "",
  });
  const [items, setItems] = useState<ChapterFunctionItemV2[]>([]);
  const [response, setResponse] = useState<ChapterFunctionsProductResponse | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(params.get("restoreCursor") || null);
  const [viewState, setViewState] = useState<ChapterFunctionsClientViewState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(
    params.get("restoreChapter") || params.get("cfChapter") || null,
  );
  const [detailItem, setDetailItem] = useState<ChapterFunctionItemV2 | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const applyPage = useCallback((page: ChapterFunctionsProductResponse, append: boolean) => {
    setResponse(page);
    setNextCursor(page.next_cursor ?? null);
    setItems((prev) => (append ? [...prev, ...(page.items || [])] : [...(page.items || [])]));
    setViewState(
      deriveChapterFunctionsViewState({
        runStatus: runStatus ?? "completed",
        fetchStatus: "success",
        response: page,
      }),
    );
    setErrorMessage(null);
  }, [runStatus]);

  const loadFirstPage = useCallback(async () => {
    if (pageMode === "running" || runStatus === "running" || runStatus === "paused") {
      setViewState("loading");
      setLoading(false);
      return;
    }
    if (pageMode === "failed" && (runStatus === "cancelled" || runStatus === "canceled")) {
      setViewState("canceled");
      setResponse({
        result_status: "canceled",
        coverage_scope: null,
        chapter_functions: null,
        items: [],
        next_cursor: null,
        total_chapters: 0,
      });
      setItems([]);
      return;
    }
    if (pageMode === "failed" && runStatus === "failed") {
      setViewState("failed");
      setItems([]);
      return;
    }
    if (runId == null || pageMode !== "completed") {
      setViewState("not_started");
      setItems([]);
      setResponse(null);
      return;
    }

    setLoading(true);
    setErrorMessage(null);
    setCursor(null);
    try {
      const page = await wholeBookFreeProductApi.getChapterFunctions(runId, {
        limit: PAGE_LIMIT,
        function: filters.function || null,
        status: filters.status || null,
      });
      applyPage(page, false);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "CHAPTER_FUNCTIONS_RESULT_ABSENT" || err.status === 404) {
          setViewState("absent");
        } else if (err.code === "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED") {
          setViewState("unsupported_contract");
          setErrorMessage(err.message);
        } else if (err.code === "CHAPTER_FUNCTIONS_INVALID_CURSOR") {
          setErrorMessage(err.message || "分页游标无效，请清除筛选后重试");
          setViewState("available");
        } else {
          setViewState("network_error");
          setErrorMessage(err.message);
        }
      } else {
        setViewState("network_error");
        setErrorMessage(err instanceof Error ? err.message : "加载失败");
      }
      setItems([]);
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }, [applyPage, filters.function, filters.status, pageMode, runId, runStatus]);

  useEffect(() => {
    void loadFirstPage();
  }, [loadFirstPage]);

  useEffect(() => {
    if (!selectedChapterId || runId == null || pageMode !== "completed") {
      setDetailItem(null);
      return;
    }
    const local = items.find((i) => String(i.chapter_id) === selectedChapterId);
    let cancelled = false;
    setDetailLoading(true);
    (async () => {
      try {
        const detail = await wholeBookFreeProductApi.getChapterFunctionChapter(
          runId,
          selectedChapterId,
        );
        const item = detail.items?.[0] ?? local ?? null;
        if (!cancelled) setDetailItem(item);
      } catch {
        if (!cancelled) setDetailItem(local ?? null);
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [items, pageMode, runId, selectedChapterId]);

  const persistFilterParams = (next: ChapterFunctionsFilters) => {
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (next.function) p.set("cfFunction", next.function);
      else p.delete("cfFunction");
      if (next.status) p.set("cfStatus", next.status);
      else p.delete("cfStatus");
      p.delete("restoreCursor");
      p.delete("restoreFunction");
      p.delete("restoreStatus");
      return p;
    });
  };

  const onFiltersChange = (next: ChapterFunctionsFilters) => {
    setFilters(next);
    setCursor(null);
    setNextCursor(null);
    persistFilterParams(next);
  };

  const onLoadMore = async () => {
    if (loadingMore || !nextCursor || runId == null) return;
    setLoadingMore(true);
    try {
      const page = await wholeBookFreeProductApi.getChapterFunctions(runId, {
        limit: PAGE_LIMIT,
        cursor: nextCursor,
        function: filters.function || null,
        status: filters.status || null,
      });
      setCursor(nextCursor);
      applyPage(page, true);
    } catch (err) {
      if (err instanceof ApiError && err.code === "CHAPTER_FUNCTIONS_INVALID_CURSOR") {
        setErrorMessage(err.message || "分页游标无效，请清除筛选后重试");
        setCursor(null);
        setNextCursor(null);
      } else {
        setErrorMessage(err instanceof Error ? err.message : "加载下一页失败");
      }
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSelectChapter = (chapterId: string) => {
    setSelectedChapterId(chapterId);
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set("cfChapter", chapterId);
      return p;
    });
  };

  const handleOpenEvidence = (evidenceId: number) => {
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (selectedChapterId) p.set("restoreChapter", selectedChapterId);
      if (filters.function) p.set("restoreFunction", filters.function);
      if (filters.status) p.set("restoreStatus", filters.status);
      if (cursor || nextCursor) p.set("restoreCursor", cursor || nextCursor || "");
      p.set("module", "chapter_functions");
      return p;
    });
    onOpenEvidence(evidenceId);
  };

  const forcedResponse: ChapterFunctionsProductResponse | null =
    pageMode === "failed" && (runStatus === "cancelled" || runStatus === "canceled")
      ? { result_status: "canceled", coverage_scope: null, chapter_functions: null, items: [], next_cursor: null, total_chapters: 0 }
      : pageMode === "failed" && runStatus === "failed"
        ? {
            result_status: "failed",
            coverage_scope: null,
            chapter_functions: null,
            items: [],
            next_cursor: null,
            total_chapters: 0,
            failure_code: null,
          }
        : response;

  return (
    <ChapterFunctionsPanel
      viewState={viewState}
      response={forcedResponse}
      items={items}
      loading={loading || pageMode === "running"}
      loadingMore={loadingMore}
      errorMessage={errorMessage}
      filters={filters}
      onFiltersChange={onFiltersChange}
      onClearFilters={() => onFiltersChange(EMPTY_FILTERS)}
      onLoadMore={() => void onLoadMore()}
      hasMore={Boolean(nextCursor)}
      selectedChapterId={selectedChapterId}
      detailItem={detailItem}
      detailLoading={detailLoading}
      onSelectChapter={handleSelectChapter}
      onCloseDetail={() => {
        setSelectedChapterId(null);
        setParams((prev) => {
          const p = new URLSearchParams(prev);
          p.delete("cfChapter");
          return p;
        });
      }}
      onOpenEvidence={handleOpenEvidence}
      onRetry={onRetry}
      onBack={onBack}
    />
  );
}
