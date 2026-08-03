/**
 * TEST-ONLY / removable harness for WB-2.2 Chapter Functions Desktop (CHG-20260803-041).
 *
 * Route: /dev/whole-book-free-chapter-functions-harness
 *
 * Purpose: Playwright + Vitest entry without final WholeBookFreeProductPage module swap
 * (Integration ownership). Safe to delete after Integration wiring.
 *
 * Query params:
 * - runId (default 42)
 * - fixture=A|B|C|...|L (optional offline fixture key; skips network)
 * - restoreChapter / restoreFunction / restoreStatus / restoreCursor — Evidence return state
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../services/apiClient";
import { wholeBookFreeProductApi } from "../services/wholeBookFreeProductApi";
import {
  deriveChapterFunctionsViewState,
  type ChapterFunctionItemV2,
  type ChapterFunctionsClientViewState,
  type ChapterFunctionsProductResponse,
} from "../services/chapterFunctionsResultV2";
import { ChapterFunctionsPanel } from "../components/wholeBookFree/chapterFunctions";
import type { ChapterFunctionsFilters } from "../components/wholeBookFree/chapterFunctions";
import {
  CHAPTER_FUNCTIONS_UI_FIXTURE_BANNER,
  CHAPTER_FUNCTIONS_UI_FIXTURES,
  longBookPage,
} from "../components/wholeBookFree/chapterFunctions/fixtures/chapterFunctionsUiFixtures";
import { openEvidenceInReader } from "../services/wholeBookFreeEvidenceDeepLink";

const EMPTY_FILTERS: ChapterFunctionsFilters = { function: "", status: "" };

type FixtureKey = keyof typeof CHAPTER_FUNCTIONS_UI_FIXTURES;

function fixtureFromKey(key: string | null): ChapterFunctionsProductResponse | null | "invalid_cursor" {
  if (!key) return null;
  if (key === "L" || key === "L0") return CHAPTER_FUNCTIONS_UI_FIXTURES.L_long_book_page0;
  if (key === "L1") return CHAPTER_FUNCTIONS_UI_FIXTURES.L_long_book_page1;
  const map: Record<string, FixtureKey> = {
    A: "A_available",
    B: "B_primary_secondary",
    C: "C_primary_null",
    D: "D_secondary_empty",
    E: "E_partial",
    F: "F_insufficient",
    G: "G_failed",
    H: "H_canceled",
    I: "I_conflict",
    M: "M_function_filter_setup",
    N: "N_status_filter_observed",
    O: "O_invalid_cursor_error" as FixtureKey,
    P: "P_unsupported_version",
    Q: "Q_evidence",
    R: "R_wb21_context_available",
    S: "S_wb21_context_absent",
    T: "T_wb21_context_insufficient",
    U: "U_empty_label",
    V: "V_non_mainline",
    W: "W_unknown",
  };
  const resolved = map[key.toUpperCase()] ?? (key as FixtureKey);
  if (resolved === ("O_invalid_cursor_error" as FixtureKey)) return "invalid_cursor";
  const hit = CHAPTER_FUNCTIONS_UI_FIXTURES[resolved];
  if (hit === null || hit === undefined) return null;
  if (typeof hit === "object" && "error_code" in hit) return "invalid_cursor";
  return hit as ChapterFunctionsProductResponse;
}

export function ChapterFunctionsHarnessPage() {
  const [params, setParams] = useSearchParams();
  const runId = Number(params.get("runId") || "42");
  const bookId = Number(params.get("bookId") || "1");
  const fixtureKey = params.get("fixture");
  const offline = Boolean(fixtureKey) || params.get("offline") === "1";

  const [filters, setFilters] = useState<ChapterFunctionsFilters>({
    function: params.get("restoreFunction") || params.get("function") || "",
    status: params.get("restoreStatus") || params.get("status") || "",
  });
  const [cursor, setCursor] = useState<string | null>(params.get("restoreCursor") || null);
  const [items, setItems] = useState<ChapterFunctionItemV2[]>([]);
  const [response, setResponse] = useState<ChapterFunctionsProductResponse | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [viewState, setViewState] = useState<ChapterFunctionsClientViewState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(
    params.get("restoreChapter") || params.get("chapter") || null,
  );
  const [detailItem, setDetailItem] = useState<ChapterFunctionItemV2 | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [evidenceOpened, setEvidenceOpened] = useState<number | null>(null);
  const [longBookPageIndex, setLongBookPageIndex] = useState(0);

  const drawerForced = params.get("drawer") === "1";

  const applyPage = useCallback(
    (page: ChapterFunctionsProductResponse, append: boolean) => {
      setResponse(page);
      setNextCursor(page.next_cursor ?? null);
      setItems((prev) => (append ? [...prev, ...(page.items || [])] : [...(page.items || [])]));
      const vs = deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "success",
        response: page,
      });
      setViewState(vs);
      setErrorMessage(null);
    },
    [],
  );

  const loadFirstPage = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    setCursor(null);
    try {
      if (offline) {
        if (fixtureKey === "J") {
          setViewState("loading");
          setLoading(true);
          return;
        }
        if (fixtureKey === "K") {
          setItems([]);
          setResponse(null);
          setViewState("absent");
          setLoading(false);
          return;
        }
        if (fixtureKey === "O") {
          setItems([]);
          setResponse(null);
          setViewState("available");
          setErrorMessage("分页游标无效，请清除筛选后重试");
          setLoading(false);
          return;
        }
        const fx = fixtureFromKey(fixtureKey);
        if (fx === "invalid_cursor") {
          setErrorMessage("分页游标无效，请清除筛选后重试");
          setViewState("available");
          setLoading(false);
          return;
        }
        if (!fx) {
          setViewState("absent");
          setLoading(false);
          return;
        }
        if (fixtureKey === "P") {
          setViewState("unsupported_contract");
          setErrorMessage("当前结果的 contract_version 不是 v2，桌面端拒绝渲染。");
          setResponse(fx);
          setLoading(false);
          return;
        }
        if (fixtureKey === "L" || fixtureKey === "L0") {
          setLongBookPageIndex(0);
          applyPage(longBookPage(0), false);
          setLoading(false);
          return;
        }
        applyPage(fx, false);
        setLoading(false);
        return;
      }

      const page = await wholeBookFreeProductApi.getChapterFunctions(runId, {
        limit: 50,
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
  }, [applyPage, filters.function, filters.status, fixtureKey, offline, runId]);

  useEffect(() => {
    void loadFirstPage();
  }, [loadFirstPage]);

  useEffect(() => {
    if (!selectedChapterId || !response) {
      setDetailItem(null);
      return;
    }
    const local = items.find((i) => String(i.chapter_id) === selectedChapterId);
    if (local && offline) {
      setDetailItem(local);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    (async () => {
      try {
        if (offline) {
          if (!cancelled) setDetailItem(local ?? null);
          return;
        }
        const detail = await wholeBookFreeProductApi.getChapterFunctionChapter(
          runId,
          selectedChapterId,
        );
        const item = detail.items?.[0] ?? null;
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
  }, [items, offline, response, runId, selectedChapterId]);

  const onFiltersChange = (next: ChapterFunctionsFilters) => {
    setFilters(next);
    setCursor(null);
    setNextCursor(null);
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (next.function) p.set("function", next.function);
      else p.delete("function");
      if (next.status) p.set("status", next.status);
      else p.delete("status");
      p.delete("restoreCursor");
      return p;
    });
  };

  const onClearFilters = () => {
    onFiltersChange(EMPTY_FILTERS);
  };

  const onLoadMore = async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      if (offline && (fixtureKey === "L" || fixtureKey === "L0" || fixtureKey === "L1")) {
        const nextIndex = longBookPageIndex + 1;
        const page = longBookPage(nextIndex);
        setLongBookPageIndex(nextIndex);
        applyPage(page, true);
        setCursor(page.next_cursor ?? null);
        return;
      }
      if (!nextCursor) return;
      if (offline) return;
      const page = await wholeBookFreeProductApi.getChapterFunctions(runId, {
        limit: 50,
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
      } else {
        setErrorMessage(err instanceof Error ? err.message : "加载下一页失败");
      }
    } finally {
      setLoadingMore(false);
    }
  };

  const onOpenEvidence = async (evidenceId: number) => {
    setEvidenceOpened(evidenceId);
    // Persist return state in query for Evidence return tests.
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (selectedChapterId) p.set("restoreChapter", selectedChapterId);
      if (filters.function) p.set("restoreFunction", filters.function);
      if (filters.status) p.set("restoreStatus", filters.status);
      if (cursor || nextCursor) p.set("restoreCursor", cursor || nextCursor || "");
      p.set("returnModule", "chapter_functions");
      return p;
    });
    try {
      if (offline) {
        // Stub: no real source fetch — expose href contract for Playwright.
        const href = `/books/${bookId}?chapter=1&paragraph=2&view=reading&evidenceId=${evidenceId}&chapterId=1&paragraphIndex=2&startOffset=1&endOffset=5&returnTo=whole-book&returnModule=chapter_functions`;
        window.history.pushState({}, "", href);
        return;
      }
      const { source } = await wholeBookFreeProductApi.getEvidenceSource(evidenceId);
      const chapterId = Number(source.chapter_index || 1);
      const href = openEvidenceInReader(bookId, source, chapterId, {
        returnModule: "chapter_functions",
      });
      window.location.assign(href);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Evidence 打开失败");
    }
  };

  const renderedItemCount = items.length;
  const banner = useMemo(() => CHAPTER_FUNCTIONS_UI_FIXTURE_BANNER, []);

  return (
    <div
      data-testid="chapter-functions-harness-page"
      data-offline={offline ? "true" : "false"}
      style={{ padding: "1rem", maxWidth: "100%", minWidth: 0 }}
    >
      <header style={{ marginBottom: "1rem" }}>
        <p data-testid="chapter-functions-harness-banner">{banner}</p>
        <p className="meta">
          TEST-ONLY harness · removable · Integration owns final Free page wiring
        </p>
        <p>
          <Link to="/library">返回书库</Link>
          {" · "}
          <span data-testid="chapter-functions-harness-run">run {runId}</span>
          {" · "}
          <span data-testid="chapter-functions-harness-item-count">{renderedItemCount}</span> items
          rendered
          {evidenceOpened != null ? (
            <>
              {" · "}
              <span data-testid="chapter-functions-harness-evidence-opened">{evidenceOpened}</span>
            </>
          ) : null}
        </p>
      </header>
      <ChapterFunctionsPanel
        viewState={loading ? "loading" : viewState}
        response={response}
        items={items}
        loading={loading}
        loadingMore={loadingMore}
        errorMessage={errorMessage}
        filters={filters}
        onFiltersChange={onFiltersChange}
        onClearFilters={onClearFilters}
        onLoadMore={() => void onLoadMore()}
        hasMore={Boolean(nextCursor)}
        selectedChapterId={selectedChapterId}
        detailItem={detailItem}
        detailLoading={detailLoading}
        onSelectChapter={setSelectedChapterId}
        onCloseDetail={() => setSelectedChapterId(null)}
        onOpenEvidence={(id) => void onOpenEvidence(id)}
        onRetry={() => void loadFirstPage()}
        useDrawerDetail={drawerForced || undefined}
      />
    </div>
  );
}
