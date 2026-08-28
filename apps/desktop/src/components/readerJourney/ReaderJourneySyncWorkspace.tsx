import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { booksApi } from "../../services/booksApi";
import { Loading, ErrorState } from "../common/States";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import {
  StructuredChapterTextPane,
  type StructuredChapterTextPaneHandle,
} from "./StructuredChapterTextPane";
import { SceneStructureDrawer } from "./SceneStructureDrawer";
import { useJourneySelection } from "../../hooks/useJourneySelection";
import type { ReaderJourneyResult, SceneResultItem } from "../../types";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import type { JourneyPageMode } from "../../types/journeySelection";
import { exportSceneCardMarkdown } from "./exportSceneCard";
import {
  applyJourneySelectionIntent,
  logJourneySelectionTransaction,
  nextJourneyTransactionId,
  type JourneySelectionIntent,
} from "./journeySelectionTransaction";
import { JourneyModeSwitcher } from "./JourneyModeSwitcher";
import "./syncWorkspace.css";

type Tab = "structure" | "evidence" | "history" | "overview" | "journey";

type Props = {
  chapterId: number;
  chapterTitle: string;
  scenes: SceneResultItem[];
  visualization: ReaderJourneyVisualization;
  tab: Tab;
  onTabChange: (tab: Tab) => void;
  taskControls?: ReactNode;
  exportBar?: ReactNode;
  /**
   * 这份旅程本身。以前这几个值是从 URL 里反推的（`/analysis-runs/:id` 或 ?analysisRun=），
   * 而书籍工作台的地址里根本没有那一段——于是导出报告拿不到任务号，直接失败。
   * 调用方手上就有这份数据，传下来即可；没传时才回退到旧的地址推断。
   */
  journeyRunId?: number | null;
  analysisRunId?: number | null;
  providerName?: string | null;
  modelName?: string | null;
  bookTitle?: string | null;
  /**
   * When embedded in Book Workspace Journey pane:
   * hide AnalysisResults legacy tabs (structure/overview/…) — primary nav already covers that.
   */
  variant?: "standalone" | "workspace";
};

async function loadAllChapterParagraphs(chapterId: number) {
  const items: { id: string; paragraph_index: number; raw_text: string }[] = [];
  let offset = 0;
  let hasMore = true;
  while (hasMore) {
    const page = await booksApi.paragraphs(chapterId, offset, 500);
    for (const p of page.items) {
      items.push({
        id: p.id,
        paragraph_index: p.paragraph_index,
        raw_text: p.raw_text,
      });
    }
    hasMore = page.has_more;
    offset += page.items.length;
    if (page.items.length === 0) break;
  }
  return items;
}

export function ReaderJourneySyncWorkspace({
  chapterId,
  chapterTitle,
  scenes,
  visualization,
  tab,
  onTabChange,
  taskControls,
  exportBar,
  journeyRunId: journeyRunIdProp,
  analysisRunId: analysisRunIdProp,
  providerName,
  modelName,
  bookTitle,
  variant = "standalone",
}: Props) {
  const textPaneRef = useRef<StructuredChapterTextPaneHandle>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sourceCollapsed, setSourceCollapsed] = useState(() => {
    try {
      const raw = localStorage.getItem("storylens.readerJourney.sourceCollapsed.v4_0");
      if (raw == null) return false;
      return JSON.parse(raw) === true || raw === "1" || raw === "true";
    } catch {
      return false;
    }
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  /** While set, Scroll Spy must not commit a different Scene (smooth/long scroll past 600ms lock). */
  const pendingProgrammaticSceneRef = useRef<number | null>(null);
  const pendingProgrammaticClearTimerRef = useRef<number | null>(null);

  const {
    state,
    selectScene,
    selectSceneByOrdinal,
    selectPhase,
    selectParagraph,
    locateEvidence,
    setMetric,
    setCluster,
    setPageMode,
    beginProgrammaticScroll,
    isScrollSpySuppressed,
  } = useJourneySelection({ scenes, enabled: true });

  const armProgrammaticScene = (ordinal: number) => {
    beginProgrammaticScroll();
    pendingProgrammaticSceneRef.current = ordinal;
    if (pendingProgrammaticClearTimerRef.current != null) {
      window.clearTimeout(pendingProgrammaticClearTimerRef.current);
    }
    // Clear guard after scroll has had time to settle; does not replace the 600ms spy lock.
    pendingProgrammaticClearTimerRef.current = window.setTimeout(() => {
      if (pendingProgrammaticSceneRef.current === ordinal) {
        pendingProgrammaticSceneRef.current = null;
      }
      pendingProgrammaticClearTimerRef.current = null;
    }, 2000);
  };

  const commitSelectionIntent = (intent: JourneySelectionIntent) => {
    const transactionId = nextJourneyTransactionId();
    setSearchParams(
      (prev) => {
        const previousSearch = prev.toString();
        const next = applyJourneySelectionIntent(prev, intent);
        logJourneySelectionTransaction({
          transactionId,
          source: intent.source,
          previousSearch,
          nextSearch: next.toString(),
        });
        return next;
      },
      { replace: true },
    );
  };

  const paragraphsQuery = useQuery({
    queryKey: ["chapter-paragraphs", chapterId],
    queryFn: () => loadAllChapterParagraphs(chapterId),
    enabled: Number.isFinite(chapterId),
  });

  useEffect(() => {
    return () => {
      if (pendingProgrammaticClearTimerRef.current != null) {
        window.clearTimeout(pendingProgrammaticClearTimerRef.current);
      }
    };
  }, []);

  const activeNode = useMemo(
    () =>
      visualization.scene_nodes.find((node) => node.scene_ordinal === state.activeSceneOrdinal),
    [visualization.scene_nodes, state.activeSceneOrdinal],
  );

  useEffect(() => {
    if (
      state.activeParagraphId &&
      state.selectionSource !== "scroll_spy" &&
      state.pageMode !== "journey"
    ) {
      beginProgrammaticScroll();
      textPaneRef.current?.scrollToParagraph(state.activeParagraphId);
    }
  }, [
    state.activeParagraphId,
    state.selectionSource,
    state.pageMode,
    beginProgrammaticScroll,
  ]);

  const handleJourneySelectionChange = (patch: {
    activeSceneOrdinal?: number | null;
    activePhaseOrdinal?: number | null;
    selectedMetric?: typeof state.selectedMetric;
    selectedQuestionClusterId?: string | null;
    evidenceParagraphIds?: string[];
    source?: typeof state.selectionSource;
  }) => {
    if (patch.selectedMetric) {
      // Workspace already atomically wrote lens+metric to the URL for rhythm/lens clicks.
      // Only mirror local controlled metric — a second URL write races and snaps the lens back.
      setMetric(patch.selectedMetric, {
        syncUrl: patch.source !== "journey_rhythm",
      });
    }
    if (patch.selectedQuestionClusterId !== undefined) {
      setCluster(patch.selectedQuestionClusterId);
    }
    if (patch.source === "journey_phase" && patch.activePhaseOrdinal !== undefined) {
      // Phase highlight only — do not jump Scene / scroll to phase start.
      selectPhase(patch.activePhaseOrdinal, "journey_phase");
    } else if (patch.activeSceneOrdinal != null) {
      armProgrammaticScene(patch.activeSceneOrdinal);
      const node = visualization.scene_nodes.find(
        (item) => item.scene_ordinal === patch.activeSceneOrdinal,
      );
      const phaseId = patch.activePhaseOrdinal ?? node?.phase_ordinal ?? null;
      const source = patch.source ?? "journey_scene";
      // Single applyPatch path: calling selectPhase without firstSceneOrdinal
      // after selectSceneByOrdinal lets syncUrl reuse a stale scene ordinal.
      if (phaseId != null) {
        selectPhase(phaseId, source, patch.activeSceneOrdinal);
      } else {
        selectSceneByOrdinal(patch.activeSceneOrdinal, source);
      }
      if (state.pageMode !== "journey") {
        textPaneRef.current?.scrollToScene(patch.activeSceneOrdinal);
      }
    }
    if (patch.evidenceParagraphIds?.length) {
      const evidenceSceneOrdinal =
        patch.activeSceneOrdinal ??
        state.activeSceneOrdinal ??
        scenes.find((s) => s.scene.id === state.activeSceneId)?.scene.ordinal ??
        null;
      if (evidenceSceneOrdinal != null) {
        armProgrammaticScene(evidenceSceneOrdinal);
      } else {
        beginProgrammaticScroll();
      }
      const sceneId =
        patch.activeSceneOrdinal != null
          ? scenes.find((s) => s.scene.ordinal === patch.activeSceneOrdinal)?.scene.id
          : state.activeSceneId;
      locateEvidence(patch.evidenceParagraphIds, sceneId);
      textPaneRef.current?.scrollToParagraph(patch.evidenceParagraphIds[0]!);
    }
  };

  const handleLocateEvidence = (paragraphId: string) => {
    if (state.activeSceneOrdinal != null) {
      armProgrammaticScene(state.activeSceneOrdinal);
    } else {
      beginProgrammaticScroll();
    }
    locateEvidence([paragraphId], state.activeSceneId);
    textPaneRef.current?.scrollToParagraph(paragraphId);
    if (state.activeSceneOrdinal != null) {
      commitSelectionIntent({
        source: "journey_evidence",
        preserveInspector: true,
        sceneOrdinal: state.activeSceneOrdinal,
        paragraphId,
      });
    }
  };

  const handleSelectSceneFromText = (sceneId: number) => {
    const item = scenes.find((s) => s.scene.id === sceneId);
    if (item) {
      armProgrammaticScene(item.scene.ordinal);
    } else {
      beginProgrammaticScroll();
    }
    selectScene(sceneId, "text_scene");
    if (item) {
      commitSelectionIntent({
        source: "scene-list",
        inspector: "scene",
        sceneOrdinal: item.scene.ordinal,
        paragraphId: item.scene.start_paragraph_id,
        clearCluster: true,
      });
    }
  };

  const handleScrollSpy = (ordinal: number) => {
    const pending = pendingProgrammaticSceneRef.current;
    if (pending != null && ordinal !== pending) {
      // Mid-flight programmatic scroll still showing Scene N-1 — do not overwrite Scene N.
      return;
    }
    if (pending != null && ordinal === pending) {
      pendingProgrammaticSceneRef.current = null;
    }
    selectSceneByOrdinal(ordinal, "scroll_spy");
    const item = scenes.find((s) => s.scene.ordinal === ordinal);
    if (item) {
      commitSelectionIntent({
        source: "scroll_spy",
        preserveInspector: true,
        sceneOrdinal: ordinal,
        paragraphId: item.scene.start_paragraph_id,
      });
    }
  };

  const handleModeChange = (mode: JourneyPageMode) => {
    setPageMode(mode);
  };

  const handleExportSceneCard = () => {
    if (!activeNode) return;
    void exportSceneCardMarkdown(activeNode, chapterTitle);
  };

  const textPane =
    paragraphsQuery.isLoading ? (
      <Loading />
    ) : paragraphsQuery.error ? (
      <ErrorState error={paragraphsQuery.error as Error} />
    ) : (
      <StructuredChapterTextPane
        ref={textPaneRef}
        chapterTitle={chapterTitle}
        scenes={scenes}
        visualization={visualization}
        paragraphs={paragraphsQuery.data ?? []}
        selection={state}
        onSelectScene={handleSelectSceneFromText}
        onSelectParagraph={(paragraphId, sceneId) =>
          selectParagraph(paragraphId, sceneId, "text_paragraph")
        }
        onScrollSpyScene={handleScrollSpy}
        isScrollSpySuppressed={isScrollSpySuppressed}
      />
    );

  // 导出报告要在附录里印模型与旅程任务号，和 journeyRunId 取的是同一份缓存结果，
  // 所以一次取全，避免三个 IIFE 各算一遍还可能算出不同的 run。
  const cachedJourney = (() => {
    if (journeyRunIdProp != null) {
      return {
        journey_run_id: journeyRunIdProp,
        analysis_run_id: analysisRunIdProp ?? null,
        provider_name: providerName ?? null,
        model_name: modelName ?? null,
      } as unknown as ReaderJourneyResult;
    }
    const fromQuery = searchParams.get("analysisRun");
    const runId =
      fromQuery && Number.isFinite(Number(fromQuery))
        ? Number(fromQuery)
        : typeof window !== "undefined"
          ? Number(window.location.pathname.match(/\/analysis-runs\/(\d+)/)?.[1])
          : NaN;
    if (!Number.isFinite(runId)) return null;
    return queryClient.getQueryData<ReaderJourneyResult>(["reader-journey", runId]) ?? null;
  })();

  // 「我要把这章带走」是一件事，不是两件。旅程面板把它的导出动作交上来，和场景卡那个
  // 并排放在页头——它产出整章七页的报告，不该是面板深处一行末尾的 12px 小标签。
  const [reportExport, setReportExport] = useState<{
    run: () => void;
    runHtml: () => void;
    busy: boolean;
  } | null>(null);

  const journeyPane = (
    <ReaderJourneyWorkspace
      onExportReady={setReportExport}
      visualization={visualization}
      chapterTitle={chapterTitle}
      onLocateEvidence={handleLocateEvidence}
      onSelectScene={(sceneId) => selectScene(sceneId, "journey_scene")}
      activeSceneOrdinal={state.activeSceneOrdinal}
      activePhaseOrdinal={state.activePhaseId}
      selectedMetric={state.selectedMetric}
      selectedQuestionClusterId={state.selectedQuestionClusterId}
      onSelectionChange={handleJourneySelectionChange}
      compactHead
      sourcePane={state.pageMode === "sync" ? textPane : undefined}
      sourceCollapsed={sourceCollapsed}
      onSourceCollapsedChange={setSourceCollapsed}
      bookTitle={bookTitle}
      analysisRunId={(() => {
        if (analysisRunIdProp != null) return analysisRunIdProp;
        const fromQuery = searchParams.get("analysisRun");
        if (fromQuery && Number.isFinite(Number(fromQuery))) return Number(fromQuery);
        if (typeof window !== "undefined") {
          const match = window.location.pathname.match(/\/analysis-runs\/(\d+)/);
          if (match?.[1]) return Number(match[1]);
        }
        return null;
      })()}
      journeyRunId={cachedJourney?.journey_run_id ?? null}
      providerName={cachedJourney?.provider_name ?? null}
      modelName={cachedJourney?.model_name ?? null}
    />
  );

  const renderMain = () => {
    if (state.pageMode === "reading") {
      return textPane;
    }
    // sync + journey: Workspace owns Source|Main|Inspector grid (no nested SplitPane).
    return journeyPane;
  };

  return (
    <div
      className="journey-sync-workspace"
      data-testid="journey-sync-workspace"
      data-variant={variant}
      data-page-mode={state.pageMode}
    >
      <header className="journey-sync-sticky-bar">
        <h1 className="journey-sync-title" data-testid="journey-sync-title">
          {/* Product title lives in journey-analysis-header; avoid duplicate visible H1. */}
          <span className="sr-only">旅程分析</span>
        </h1>
        {variant === "standalone" ? (
          <div className="journey-sync-tabs tabs">
            <button
              data-testid="tab-structure"
              className={tab === "structure" ? "active" : ""}
              onClick={() => onTabChange("structure")}
            >
              场景结构
            </button>
            <button
              data-testid="tab-evidence"
              className={tab === "evidence" ? "active" : ""}
              onClick={() => onTabChange("evidence")}
            >
              证据
            </button>
            <button
              data-testid="tab-history"
              className={tab === "history" ? "active" : ""}
              onClick={() => onTabChange("history")}
            >
              历史
            </button>
            <button
              data-testid="tab-overview"
              className={tab === "overview" ? "active" : ""}
              onClick={() => onTabChange("overview")}
            >
              整章概览
            </button>
            <button
              data-testid="tab-journey"
              className={tab === "journey" ? "active" : ""}
              onClick={() => onTabChange("journey")}
            >
              读者旅程
            </button>
          </div>
        ) : null}

        <JourneyModeSwitcher pageMode={state.pageMode} onChange={handleModeChange} />

        <div className="journey-sync-actions">
          <button
            type="button"
            data-testid="open-scene-structure-drawer"
            onClick={() => setDrawerOpen(true)}
          >
            章节结构
          </button>
          <span className="journey-export-group" data-testid="journey-export-group">
            <span className="journey-export-group__label">导出</span>
            {reportExport && (
              <>
                <button
                  type="button"
                  data-testid="journey-export-report-pdf"
                  title="整章的结构化评测报告：三项判断、追读曲线、悬念账本、逐场证据 · 7 页 A4"
                  disabled={reportExport.busy}
                  onClick={reportExport.run}
                >
                  {reportExport.busy ? "正在生成…" : "本章报告 · PRO"}
                </button>
                <button
                  type="button"
                  data-testid="journey-export-report-html"
                  title="免费基础阅读版：本章判断、阶段与场景概览"
                  disabled={reportExport.busy}
                  onClick={reportExport.runHtml}
                >
                  基础 HTML
                </button>
              </>
            )}
            {activeNode && (
              <button
                type="button"
                data-testid="export-scene-card"
                title="只导出正在看的这一个场景 · Markdown"
                onClick={handleExportSceneCard}
              >
                当前场景卡
              </button>
            )}
          </span>
        </div>

        {exportBar}
      </header>

      {taskControls && (
        <details className="journey-task-controls" data-testid="journey-task-controls">
          <summary>任务控制</summary>
          {taskControls}
        </details>
      )}

      <div className="journey-sync-main">{renderMain()}</div>

      <SceneStructureDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        scenes={scenes}
        visualization={visualization}
        activeSceneOrdinal={state.activeSceneOrdinal}
        onSelectScene={(sceneId) => selectScene(sceneId, "drawer")}
      />
    </div>
  );
}
