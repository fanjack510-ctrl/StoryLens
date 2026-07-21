import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookWorkspacePage } from "./BookWorkspacePage";
import { CompactToolbar } from "../components/layout/CompactToolbar";
import { OverflowMenu } from "../components/layout/OverflowMenu";
import { ReadingSettingsPopover } from "../components/layout/ReadingSettingsPopover";
import { ResultViewSwitcher } from "../components/layout/ResultViewSwitcher";
import { StartAnalysisDialog } from "../components/analysis/StartAnalysisDialog";
import { BoundaryReviewPanel } from "../components/analysis/BoundaryReviewPanel";
import { ReparseDialog } from "../components/books/ReparseDialog";
import { UnifiedAnalysisRecoveryCard } from "../components/chapterAnalysis/UnifiedAnalysisRecoveryCard";
import { ChapterAnalysisProgressPanel } from "../components/chapterAnalysis/ChapterAnalysisProgressPanel";
import { ReaderJourneyProgressCard } from "../components/chapterAnalysis/ReaderJourneyProgressCard";
import { EmbeddedAnalysisResultShell } from "../components/chapterResult/EmbeddedAnalysisResultShell";
import { StateView } from "../components/ui/StateView";
import { useCurrentPageAnalysisProgress } from "../hooks/useCurrentPageAnalysisProgress";
import { analysisApi } from "../services/analysisApi";
import { analysisRecoveryApi } from "../services/analysisRecoveryApi";
import { booksApi } from "../services/booksApi";
import {
  getOrCreateJourneyClientRequestId,
  isSceneAnalysisComplete,
  mapChapterCompositionState,
} from "../services/chapterJourneyComposition";
import { discoverActiveChapterRun } from "../services/discoverActiveChapterRun";
import { useUiStore } from "../stores/uiStore";

type ChapterView = "reading" | "progress" | "result";

function parsePositiveInt(value: string | null): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function clickResults(selector: string) {
  document.querySelector<HTMLElement>(selector)?.dispatchEvent(
    new MouseEvent("click", { bubbles: true, cancelable: true }),
  );
  document.querySelector<HTMLButtonElement | HTMLAnchorElement>(selector)?.click();
}

function resolveView(
  explicit: string | null,
  uiState: string,
  analysisRunId: number | null,
): ChapterView {
  if (explicit === "reading" || explicit === "progress" || explicit === "result") {
    return explicit;
  }
  if (!analysisRunId) return "reading";
  if (uiState === "succeeded") return "result";
  if (
    uiState === "running" ||
    uiState === "creating" ||
    uiState === "partial" ||
    uiState === "failed" ||
    uiState === "boundary_review_required" ||
    uiState === "awaiting_budget_adjustment" ||
    uiState === "aborted_by_limit" ||
    uiState === "provider_recovery"
  ) {
    return "progress";
  }
  return "reading";
}

export function BookRoutePage() {
  const params = useParams();
  const bookId = Number(params.bookId || 1);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [dialog, setDialog] = useState(false);
  const [reparseOpen, setReparseOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [techOpen, setTechOpen] = useState(false);
  const [chapterInfoOpen, setChapterInfoOpen] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [analysisInfoOpen, setAnalysisInfoOpen] = useState(false);
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [budgetModalOpen, setBudgetModalOpen] = useState(false);
  const [budgetModalRunId, setBudgetModalRunId] = useState<number | null>(null);
  /** In-memory only: survives polling, clears on full page refresh/remount. */
  const seenBudgetModalRef = useRef<Set<number>>(new Set());
  const qc = useQueryClient();
  const { contentWidth, showParagraphIds } = useUiStore();

  const analysisRunFromUrl = parsePositiveInt(searchParams.get("analysisRun"));
  const chapterFromUrl = parsePositiveInt(searchParams.get("chapter"));

  const book = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId),
    enabled: !!bookId,
  });
  const chapters = useQuery({
    queryKey: ["chapters", bookId],
    queryFn: () => booksApi.chapters(bookId),
    enabled: !!bookId,
  });
  const recentRuns = useQuery({
    queryKey: ["runs", bookId],
    queryFn: () => analysisApi.runs(),
    refetchOnWindowFocus: true,
  });

  const defaultChapterId = useMemo(() => {
    const list = chapters.data || [];
    const first = list.find((item) => item.section_type === "chapter") || list[0];
    return first?.id || 0;
  }, [chapters.data]);

  const [selectedChapterId, setSelectedChapterId] = useState(0);
  const chapterId = chapterFromUrl || selectedChapterId || defaultChapterId;

  useEffect(() => {
    if (!selectedChapterId && defaultChapterId) setSelectedChapterId(defaultChapterId);
  }, [defaultChapterId, selectedChapterId]);

  // Ensure chapter= is present (internal Chapter ID, not display ordinal).
  useEffect(() => {
    if (!chapterId || chapterFromUrl === chapterId) return;
    if (chapterFromUrl) return;
    setSearchParams(
      (prev) => {
        if (prev.get("chapter")) return prev;
        const next = new URLSearchParams(prev);
        next.set("chapter", String(chapterId));
        return next;
      },
      { replace: true },
    );
  }, [chapterId, chapterFromUrl, setSearchParams]);

  // Auto-discover active AnalysisRun when URL omits analysisRun (no create, no model calls).
  useEffect(() => {
    if (analysisRunFromUrl) return;
    if (!chapterId || !recentRuns.data) return;
    const discovered = discoverActiveChapterRun(recentRuns.data, chapterId);
    if (!discovered) return;
    setPanelCollapsed(false);
    setSearchParams(
      (prev) => {
        if (prev.get("analysisRun")) return prev;
        const next = new URLSearchParams(prev);
        next.set("chapter", String(chapterId));
        next.set("analysisRun", String(discovered.id));
        const active =
          discovered.status !== "succeeded" &&
          discovered.status !== "cancelled" &&
          discovered.status !== "review_cancelled";
        if (active) next.set("view", "progress");
        else if (!prev.get("view")) next.set("view", "result");
        return next;
      },
      { replace: true },
    );
  }, [analysisRunFromUrl, chapterId, recentRuns.data, setSearchParams]);

  const analysisRunId = analysisRunFromUrl;

  // Alias resultTab → tab for frozen journey URL semantics
  useEffect(() => {
    const resultTab = searchParams.get("resultTab");
    if (resultTab === "reader-journey" && searchParams.get("tab") !== "reader-journey") {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("tab", "reader-journey");
          next.delete("resultTab");
          return next;
        },
        { replace: true },
      );
    } else if (resultTab === "analysis" && searchParams.get("tab") === "reader-journey") {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete("tab");
          next.delete("resultTab");
          return next;
        },
        { replace: true },
      );
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const root = document.querySelector(".book-shell-body .structure-pane");
    if (!root || !chapters.data?.length) return;
    const onClick = (event: Event) => {
      const button = (event.target as HTMLElement).closest("button");
      if (!button || !root.contains(button)) return;
      const list = chapters.data || [];
      const match = list.find((c) => {
        const title = c.display_title || c.title || "";
        return title && button.textContent?.includes(title);
      });
      if (!match) return;
      setSelectedChapterId(match.id);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("chapter", String(match.id));
          // Drop bound run so the new chapter re-discovers its own AnalysisRun.
          next.delete("analysisRun");
          next.delete("view");
          return next;
        },
        { replace: true },
      );
    };
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
  }, [chapters.data, setSearchParams]);

  const progress = useCurrentPageAnalysisProgress({
    runId: analysisRunId,
    enabled: !!analysisRunId,
  });

  // Keep chapter= aligned with the bound run's subject_id (internal Chapter ID).
  useEffect(() => {
    if (!analysisRunId || !progress.run) return;
    const runChapterId = Number(progress.run.subject_id);
    if (!Number.isFinite(runChapterId) || runChapterId <= 0) return;
    if (runChapterId === chapterId) return;
    setSelectedChapterId(runChapterId);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("chapter", String(runChapterId));
        next.set("analysisRun", String(analysisRunId));
        return next;
      },
      { replace: true },
    );
  }, [analysisRunId, progress.run?.id, progress.run?.subject_id, chapterId, setSearchParams]);

  const view = resolveView(searchParams.get("view"), progress.uiState, analysisRunId);

  // Auto-enter result view when Run succeeds (unless user chose reading).
  useEffect(() => {
    if (progress.uiState !== "succeeded" || !analysisRunId) return;
    const explicit = searchParams.get("view");
    if (explicit === "reading" || explicit === "result") return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("view", "result");
        next.set("analysisRun", String(analysisRunId));
        if (chapterId) next.set("chapter", String(chapterId));
        return next;
      },
      { replace: true },
    );
  }, [progress.uiState, analysisRunId, searchParams, setSearchParams, chapterId]);

  const sceneComplete = isSceneAnalysisComplete(progress.run);
  const journey = useQuery({
    queryKey: ["reader-journey", analysisRunId],
    queryFn: () => analysisApi.readerJourney(analysisRunId!),
    enabled: !!analysisRunId && (progress.uiState === "succeeded" || sceneComplete),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (
        status &&
        ["queued", "running", "scene_profiles_running", "chapter_synthesis_running"].includes(
          status,
        )
      ) {
        return 2000;
      }
      return false;
    },
  });
  const compositionUiState = mapChapterCompositionState(progress.run, journey.data);
  const hasJourney = Boolean(
    journey.data?.status === "succeeded" && journey.data.visualization,
  );
  const isJourneyTab = searchParams.get("tab") === "reader-journey";
  const journeyRunId = journey.data?.journey_run_id ?? null;
  const journeyFailed = Boolean(
    journey.data?.status &&
      ["failed", "scene_profiles_partial", "budget_blocked"].includes(journey.data.status),
  );
  const journeyProgress = useQuery({
    queryKey: ["reader-journey-progress", journeyRunId],
    queryFn: () => analysisApi.readerJourneyProgress(journeyRunId!),
    enabled:
      !!journeyRunId &&
      (compositionUiState === "reader_journey_processing" ||
        Boolean(
          journey.data?.status &&
            ["failed", "scene_profiles_partial", "budget_blocked"].includes(journey.data.status),
        )),
    refetchInterval: compositionUiState === "reader_journey_processing" ? 2000 : false,
  });

  // After journey generation finishes, open ReaderJourneyWorkspace once.
  const prevCompositionRef = useRef(compositionUiState);
  useEffect(() => {
    const prev = prevCompositionRef.current;
    prevCompositionRef.current = compositionUiState;
    if (!hasJourney || !analysisRunId) return;
    if (compositionUiState !== "succeeded") return;
    if (prev !== "reader_journey_processing") return;
    setSearchParams(
      (params) => {
        const next = new URLSearchParams(params);
        next.set("view", "result");
        next.set("tab", "reader-journey");
        next.set("analysisRun", String(analysisRunId));
        return next;
      },
      { replace: true },
    );
  }, [hasJourney, compositionUiState, analysisRunId, setSearchParams]);

  const chapterTitle = useMemo(() => {
    const list = chapters.data || [];
    const fromRun = progress.run?.subject_id
      ? list.find((c) => String(c.id) === String(progress.run?.subject_id))
      : undefined;
    const current = list.find((c) => c.id === chapterId);
    const target = fromRun || current;
    return target?.display_title || target?.title;
  }, [chapters.data, chapterId, progress.run?.subject_id]);

  const runs = Array.isArray(recentRuns.data) ? recentRuns.data : [];
  const latestSucceeded = runs.find(
    (run) =>
      run.status === "succeeded" && chapterId && String(run.subject_id) === String(chapterId),
  );

  const showProgressPanel =
    view === "progress" && Boolean(analysisRunId) && !panelCollapsed;
  const showRunningBanner =
    view === "reading" &&
    Boolean(analysisRunId) &&
    (progress.uiState === "running" ||
      progress.uiState === "boundary_review_required" ||
      progress.uiState === "awaiting_budget_adjustment" ||
      progress.uiState === "provider_recovery");
  const showCompleteBanner =
    view === "reading" && Boolean(analysisRunId) && compositionUiState === "succeeded";
  const showSceneCompleteBanner =
    view === "reading" &&
    Boolean(analysisRunId) &&
    compositionUiState === "awaiting_reader_journey_start";
  const showJourneyProcessingBanner =
    view === "reading" &&
    Boolean(analysisRunId) &&
    compositionUiState === "reader_journey_processing";

  useEffect(() => {
    if (progress.uiState !== "awaiting_budget_adjustment" || !progress.run) return;
    const runId = progress.run.id;
    if (seenBudgetModalRef.current.has(runId)) return;
    seenBudgetModalRef.current.add(runId);
    setBudgetModalRunId(runId);
    setBudgetModalOpen(true);
  }, [progress.uiState, progress.run?.id]);

  const setView = (next: ChapterView) => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("view", next);
        if (analysisRunId) params.set("analysisRun", String(analysisRunId));
        if (chapterId) params.set("chapter", String(chapterId));
        if (next !== "result") {
          params.delete("tab");
          params.delete("mode");
          params.delete("scene");
          params.delete("paragraph");
          params.delete("metric");
          params.delete("cluster");
          params.delete("resultTab");
        }
        return params;
      },
      { replace: true },
    );
    if (next === "progress") setPanelCollapsed(false);
  };

  const setResultTab = (tab: "analysis" | "journey") => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("view", "result");
        if (tab === "journey") {
          params.set("tab", "reader-journey");
          // Only click into frozen journey pane when visualization already exists.
          if (hasJourney) {
            queueMicrotask(() => clickResults('[data-testid="tab-journey"]'));
          }
        } else {
          params.delete("tab");
          params.delete("mode");
          params.delete("scene");
          params.delete("paragraph");
          params.delete("metric");
          params.delete("cluster");
          queueMicrotask(() => clickResults('[data-testid="tab-structure"]'));
        }
        return params;
      },
      { replace: true },
    );
  };

  const bindAnalysisRun = (runId: number) => {
    setPanelCollapsed(false);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("analysisRun", String(runId));
        next.set("view", "progress");
        if (chapterId) next.set("chapter", String(chapterId));
        return next;
      },
      { replace: true },
    );
  };

  const selectChapterFromCatalog = (id: number) => {
    setSelectedChapterId(id);
    setCatalogOpen(false);
    setSearchParams(
      () => {
        const next = new URLSearchParams();
        next.set("chapter", String(id));
        // Omit analysisRun so discovery binds the target chapter's run only.
        return next;
      },
      { replace: true },
    );
  };

  useEffect(() => {
    if (!catalogOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setCatalogOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [catalogOpen]);

  const bookTitle = book.data?.title || "书籍";
  const chapterCount = (chapters.data || []).length;

  const moreItems =
    view === "result"
      ? [
          {
            id: "overview",
            label: "整章概览",
            group: "查看",
            testId: "book-more-overview",
            onSelect: () => {
              setResultTab("analysis");
              queueMicrotask(() => clickResults('[data-testid="tab-overview"]'));
            },
          },
          {
            id: "history",
            label: "历史版本",
            group: "查看",
            testId: "book-more-history",
            onSelect: () => {
              setResultTab("analysis");
              queueMicrotask(() => clickResults('[data-testid="tab-history"]'));
            },
          },
          {
            id: "analysis-info",
            label: "分析信息",
            group: "查看",
            testId: "book-more-analysis-info",
            onSelect: () => setAnalysisInfoOpen(true),
          },
          {
            id: "tech",
            label: "技术信息",
            group: "查看",
            testId: "book-more-tech",
            onSelect: () => setTechOpen(true),
          },
          {
            id: "export-png",
            label: "导出旅程PNG",
            group: "导出",
            testId: "book-more-export-png",
            onSelect: () => {
              clickResults('[data-testid="journey-more-chart-settings"]');
              queueMicrotask(() => clickResults('[data-testid="journey-export-png"]'));
            },
          },
          {
            id: "export-json",
            label: "导出JSON",
            group: "导出",
            testId: "book-more-export-json",
            onSelect: () => clickResults('[data-testid="export-json"]'),
          },
          {
            id: "export-md",
            label: "导出Markdown",
            group: "导出",
            testId: "book-more-export-md",
            onSelect: () => clickResults('[data-testid="export-markdown"]'),
          },
          {
            id: "export-journey-json",
            label: "导出旅程JSON",
            group: "导出",
            testId: "book-more-export-journey-json",
            onSelect: () => clickResults('[data-testid="export-journey-json"]'),
          },
          {
            id: "tasks",
            label: "查看任务记录",
            group: "操作",
            testId: "book-more-tasks",
            onSelect: () => navigate(analysisRunId ? `/tasks?run_id=${analysisRunId}` : "/tasks"),
          },
          {
            id: "reanalyze",
            label: "重新分析",
            group: "操作",
            testId: "book-more-reanalyze",
            onSelect: () => setDialog(true),
          },
          {
            id: "boundary",
            label: "高级边界审阅",
            group: "操作",
            testId: "book-more-boundary-review",
            onSelect: () => setReviewOpen(true),
          },
        ]
      : [
          {
            id: "full-text",
            label: "完整正文",
            group: "查看",
            testId: "book-more-full-text",
            onSelect: () => {
              const buttons = Array.from(
                document.querySelectorAll<HTMLButtonElement>(
                  ".book-shell-simplified .reader-tools button",
                ),
              );
              buttons.find((btn) => btn.textContent?.includes("完整正文"))?.click();
            },
          },
          {
            id: "boundary-review",
            label: "场景边界审阅",
            group: "查看",
            testId: "book-more-boundary-review",
            onSelect: () => setReviewOpen(true),
          },
          {
            id: "tasks",
            label: "查看任务记录",
            group: "查看",
            testId: "book-more-tasks",
            onSelect: () => navigate(analysisRunId ? `/tasks?run_id=${analysisRunId}` : "/tasks"),
          },
          {
            id: "reparse",
            label: "重新识别章节",
            group: "操作",
            testId: "book-more-reparse",
            onSelect: () => setReparseOpen(true),
          },
          {
            id: "chapter-info",
            label: "章节信息",
            group: "查看",
            testId: "book-more-chapter-info",
            onSelect: () => setChapterInfoOpen(true),
          },
          {
            id: "tech",
            label: "技术信息",
            group: "查看",
            testId: "book-more-tech",
            onSelect: () => setTechOpen(true),
          },
        ];

  const startAnalysisDisabled =
    !chapterId ||
    Boolean(
      analysisRunId &&
        progress.run &&
        String(progress.run.subject_id) === String(chapterId) &&
        (progress.uiState === "running" ||
          progress.uiState === "boundary_review_required" ||
          progress.uiState === "awaiting_budget_adjustment"),
    );

  const readingToolbarTitle = (
    <div className="workspace-toolbar-identity">
      <button
        type="button"
        className="ghost workspace-back-library"
        data-testid="workspace-back-library"
        onClick={() => navigate("/library")}
      >
        ‹ 返回书库
      </button>
      <span className="workspace-toolbar-titles">
        <span className="workspace-toolbar-book" title={bookTitle}>
          {bookTitle}
        </span>
        {chapterTitle ? (
          <span className="workspace-toolbar-chapter" title={chapterTitle}>
            {chapterTitle}
          </span>
        ) : null}
      </span>
      <button
        type="button"
        className="ghost workspace-catalog-trigger"
        data-testid="book-chapter-catalog"
        onClick={() => setCatalogOpen(true)}
      >
        章节目录
      </button>
    </div>
  );

  const resultToolbarTitle = (
    <div className="workspace-toolbar-identity">
      <button
        type="button"
        className="ghost workspace-back-library"
        data-testid="workspace-back-library"
        onClick={() => navigate("/library")}
      >
        ‹ 返回书库
      </button>
      <button
        type="button"
        className="ghost"
        data-testid="book-chapter-catalog"
        onClick={() => setCatalogOpen(true)}
      >
        章节目录
      </button>
    </div>
  );

  return (
    <div
      className="book-shell-simplified workspace-shell"
      data-testid="book-chapter-shell"
      data-content-width={contentWidth}
      data-show-paragraph-ids={showParagraphIds ? "true" : "false"}
      data-analysis-run={analysisRunId ? String(analysisRunId) : undefined}
      data-view={view}
      data-catalog-open={catalogOpen ? "true" : "false"}
      data-has-progress={showProgressPanel ? "true" : "false"}
    >
      <CompactToolbar
        className="workspace-toolbar"
        data-testid="book-shell-toolbar"
        title={view === "result" ? resultToolbarTitle : readingToolbarTitle}
        primary={
          view === "result" && sceneComplete ? (
            <ResultViewSwitcher
              active={isJourneyTab ? "journey" : "analysis"}
              onChange={(v) => setResultTab(v)}
              journeyAvailable
              analysisLabel="场景分析"
              journeyLabel="阅读旅程"
            />
          ) : view === "result" ? (
            <span className="secondary" data-testid="book-result-analysis-label">
              场景分析
            </span>
          ) : (
            <button
              type="button"
              className="primary"
              data-testid="shell-start-analysis"
              disabled={startAnalysisDisabled}
              onClick={() => setDialog(true)}
            >
              开始分析
            </button>
          )
        }
        secondary={
          view === "result" ? (
            <button
              type="button"
              className="secondary"
              data-testid="book-view-reading"
              onClick={() => setView("reading")}
            >
              正文阅读
            </button>
          ) : (
            <>
              <ReadingSettingsPopover />
              {panelCollapsed && analysisRunId ? (
                <button
                  type="button"
                  className="secondary"
                  data-testid="chapter-analysis-expand"
                  onClick={() => {
                    setPanelCollapsed(false);
                    setView("progress");
                  }}
                >
                  展开分析面板
                </button>
              ) : null}
              {latestSucceeded && !analysisRunId && (
                <Link
                  className="secondary"
                  data-testid="view-recent-analysis"
                  to={`/analysis-runs/${latestSucceeded.id}/results`}
                >
                  查看最近分析
                </Link>
              )}
              {(compositionUiState === "succeeded" ||
                compositionUiState === "awaiting_reader_journey_start" ||
                compositionUiState === "reader_journey_processing") &&
                analysisRunId &&
                view === "reading" && (
                <button
                  type="button"
                  className="secondary"
                  data-testid="book-view-result"
                  onClick={() => setView("result")}
                >
                  {compositionUiState === "awaiting_reader_journey_start"
                    ? "查看场景分析"
                    : compositionUiState === "reader_journey_processing"
                      ? "查看阅读旅程进度"
                      : "查看分析结果"}
                </button>
              )}
            </>
          )
        }
        tertiary={<OverflowMenu data-testid="book-more-menu" items={moreItems} />}
      />

      {chapterInfoOpen && (
        <div className="shell-banner" data-testid="chapter-info-banner">
          <span>
            {book.data?.title || "书籍"} · {(chapters.data || []).length} 个分区
          </span>
          <button type="button" onClick={() => setChapterInfoOpen(false)}>
            关闭
          </button>
        </div>
      )}

      {techOpen && (
        <div className="shell-banner tech-info" data-testid="book-tech-info">
          <span>
            Book ID {bookId}
            {analysisRunId ? ` · analysisRun ${analysisRunId}` : ""}
            {book.data?.source_file_hash
              ? ` · Hash ${book.data.source_file_hash.slice(0, 12)}…`
              : ""}
          </span>
          <button type="button" onClick={() => setTechOpen(false)}>
            关闭
          </button>
        </div>
      )}

      {analysisInfoOpen && progress.run && (
        <div className="shell-banner tech-info" data-testid="book-analysis-info">
          <span>
            Scene {progress.run.total_scene_count ?? "—"}
            {progress.run.completed_at
              ? ` · 完成 ${new Date(progress.run.completed_at).toLocaleString()}`
              : ""}
            {typeof progress.run.budget_required?.estimated_cost === "number"
              ? ` · 预估 ${progress.run.budget_required.estimated_cost} CNY`
              : ""}
          </span>
          <button type="button" onClick={() => setAnalysisInfoOpen(false)}>
            关闭
          </button>
        </div>
      )}

      {showRunningBanner && (
        <div className="book-shell-running-banner" data-testid="chapter-analysis-running-banner">
          <span>
            {progress.uiState === "awaiting_budget_adjustment"
              ? `${chapterTitle || "当前章节"}分析已暂停：今日云端请求额度不足`
              : `${chapterTitle || "当前章节"}正在分析`}
          </span>
          <button type="button" onClick={() => setView("progress")}>
            查看进度
          </button>
        </div>
      )}

      {showCompleteBanner && (
        <div className="book-shell-complete-banner" data-testid="chapter-analysis-complete-banner">
          <span>Scene与阅读旅程已完成</span>
          <button
            type="button"
            data-testid="banner-open-result"
            onClick={() => {
              setResultTab("journey");
            }}
          >
            查看阅读旅程
          </button>
        </div>
      )}

      {showSceneCompleteBanner && (
        <div
          className="book-shell-complete-banner"
          data-testid="chapter-analysis-scene-complete-banner"
        >
          <span>分析已暂停 · 阅读旅程尚未生成</span>
          <button
            type="button"
            data-testid="banner-continue-reader-journey"
            onClick={() => setResultTab("journey")}
          >
            修复并继续
          </button>
        </div>
      )}

      {showJourneyProcessingBanner && (
        <div
          className="book-shell-running-banner"
          data-testid="chapter-analysis-journey-banner"
        >
          <span>正在生成阅读旅程</span>
          <button type="button" onClick={() => setResultTab("journey")}>
            查看进度
          </button>
        </div>
      )}

      {reviewOpen && chapterId ? (
        <div className="shell-review-focus" data-testid="shell-boundary-review">
          <BoundaryReviewPanel
            bookId={bookId}
            chapterId={chapterId}
            chapterTitle={chapterTitle}
            onExit={() => setReviewOpen(false)}
            onConfirmed={({ runId, budgetBlocked }) => {
              if (runId) bindAnalysisRun(runId);
              setReviewOpen(false);
              setPanelCollapsed(false);
              setView("progress");
              if (budgetBlocked && runId) {
                seenBudgetModalRef.current.add(runId);
                setBudgetModalRunId(runId);
                setBudgetModalOpen(true);
              }
              void progress.refresh();
            }}
          />
        </div>
      ) : (
        <div
          className="book-shell-body"
          data-has-progress={showProgressPanel ? "true" : "false"}
          data-view={view}
          data-testid="book-shell-body"
        >
          {view !== "result" && (
            <div className="book-shell-workspace">
              <BookWorkspacePage />
            </div>
          )}
          {showProgressPanel && (
            <ChapterAnalysisProgressPanel
              run={progress.run}
              uiState={
                progress.isLoading && !progress.run
                  ? "creating"
                  : compositionUiState !== "idle"
                    ? compositionUiState
                    : progress.uiState === "idle" && analysisRunId
                      ? "running"
                      : progress.uiState
              }
              chapterTitle={chapterTitle}
              reconnectHint={progress.reconnectHint}
              canResume={progress.canResume}
              onResume={progress.resume}
              onReanalyze={() => setDialog(true)}
              onReviewBoundary={() => setReviewOpen(true)}
              onDismiss={() => setPanelCollapsed(true)}
              onContinueReading={() => setView("reading")}
              onViewResults={() => {
                setResultTab("analysis");
              }}
              onContinueReaderJourney={() => setResultTab("journey")}
              onBudgetContinued={() => void progress.refresh()}
            />
          )}
          {view === "result" && analysisRunId ? (
            <>
              {isJourneyTab && journeyFailed ? (
                <StateView
                  kind="error"
                  data-testid="journey-failed"
                  title="阅读旅程生成失败"
                  description="已完成的场景分析不会受到影响。"
                  primaryAction={{
                    label: "重新生成",
                    testId: "journey-failed-retry",
                    onClick: () => {
                      void (async () => {
                        try {
                          if (journeyRunId) {
                            await analysisApi.resumeReaderJourney(journeyRunId, {
                              client_request_id: getOrCreateJourneyClientRequestId(analysisRunId),
                              cloud_consent: true,
                              confirmed: true,
                            });
                          } else if (progress.run) {
                            await analysisRecoveryApi.recover(progress.run.id, {
                              client_request_id: getOrCreateJourneyClientRequestId(analysisRunId),
                              cloud_consent: true,
                              confirmed: true,
                              recovery_mode: "unified",
                              resume: true,
                            });
                          }
                        } finally {
                          void qc.invalidateQueries({
                            queryKey: ["reader-journey", analysisRunId],
                          });
                          void journey.refetch();
                          void progress.refresh();
                        }
                      })();
                    },
                  }}
                  secondaryAction={{
                    label: "查看任务详情",
                    testId: "journey-failed-task-details",
                    onClick: () => navigate(`/tasks?run_id=${analysisRunId}`),
                  }}
                />
              ) : null}
              {isJourneyTab &&
              compositionUiState === "awaiting_reader_journey_start" &&
              !journeyFailed &&
              progress.run ? (
                <UnifiedAnalysisRecoveryCard
                  run={progress.run}
                  variant="card"
                  onContinued={() => {
                    void qc.invalidateQueries({ queryKey: ["reader-journey", analysisRunId] });
                    void journey.refetch();
                    void progress.refresh();
                  }}
                />
              ) : null}
              {isJourneyTab && compositionUiState === "reader_journey_processing" ? (
                <ReaderJourneyProgressCard
                  analysisRunId={analysisRunId}
                  progress={journeyProgress.data}
                  loading={journeyProgress.isLoading && !journeyProgress.data}
                  errorMessage={
                    journeyProgress.data?.user_error_message ||
                    journeyProgress.data?.root_error_message ||
                    null
                  }
                  onViewTaskDetails={() => navigate(`/tasks?run_id=${analysisRunId}`)}
                />
              ) : null}
              {!(
                isJourneyTab &&
                (journeyFailed ||
                  compositionUiState === "awaiting_reader_journey_start" ||
                  compositionUiState === "reader_journey_processing")
              ) ? (
                <EmbeddedAnalysisResultShell
                  runId={analysisRunId}
                  onReading={() => setView("reading")}
                />
              ) : null}
              {isJourneyTab &&
              compositionUiState === "awaiting_reader_journey_start" &&
              !journeyFailed &&
              !progress.run ? (
                <p className="notice" data-testid="reader-journey-resume-loading-run">
                  正在加载分析任务…
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      )}

      {catalogOpen && (
        <div
          className="chapter-catalog-drawer"
          data-testid="chapter-catalog-drawer"
          onClick={(event) => {
            if (event.target === event.currentTarget) setCatalogOpen(false);
          }}
        >
          <div
            className="chapter-catalog-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="chapter-catalog-title"
          >
            <div className="chapter-catalog-head">
              <h3 id="chapter-catalog-title">章节目录</h3>
              <button
                type="button"
                className="chapter-catalog-close"
                aria-label="关闭"
                data-testid="chapter-catalog-close"
                onClick={() => setCatalogOpen(false)}
              >
                ×
              </button>
            </div>
            <div className="chapter-catalog-context">
              <strong className="chapter-catalog-book" title={bookTitle}>
                {bookTitle}
              </strong>
              <span className="chapter-catalog-count">共 {chapterCount} 章</span>
            </div>
            <div className="chapter-catalog-list">
              {(chapters.data || []).map((c) => {
                const title = c.display_title || c.title;
                const num =
                  c.section_type === "front_matter"
                    ? "资料"
                    : String(c.chapter_number_normalized || c.chapter_index).padStart(2, "0");
                return (
                  <button
                    key={c.id}
                    type="button"
                    className={`chapter-catalog-item${c.id === chapterId ? " active" : ""}`}
                    data-testid={`catalog-chapter-${c.id}`}
                    title={title}
                    onClick={() => selectChapterFromCatalog(c.id)}
                  >
                    <span className="chapter-catalog-item-num">{num}</span>
                    <span className="chapter-catalog-item-title">{title}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {budgetModalOpen &&
      progress.run &&
      (progress.uiState === "awaiting_budget_adjustment" ||
        progress.uiState === "provider_recovery" ||
        budgetModalRunId === progress.run.id) ? (
        <UnifiedAnalysisRecoveryCard
          run={progress.run}
          variant="modal"
          onClose={() => {
            setBudgetModalOpen(false);
            setBudgetModalRunId(null);
          }}
          onContinued={() => {
            setBudgetModalOpen(false);
            setBudgetModalRunId(null);
            void progress.refresh();
          }}
          onLater={() => {
            setBudgetModalOpen(false);
            setBudgetModalRunId(null);
          }}
        />
      ) : null}

      {dialog && chapterId ? (
        <StartAnalysisDialog
          chapterId={chapterId}
          onClose={() => setDialog(false)}
          onCreated={(runId) => {
            bindAnalysisRun(runId);
            setDialog(false);
          }}
        />
      ) : null}

      {reparseOpen && (
        <ReparseDialog
          bookId={bookId}
          onClose={() => setReparseOpen(false)}
          onDone={async (id) => {
            setReparseOpen(false);
            await qc.invalidateQueries({ queryKey: ["chapters", bookId] });
            if (id !== bookId) location.href = `/books/${id}`;
          }}
        />
      )}
    </div>
  );
}
