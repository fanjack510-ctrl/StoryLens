import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookWorkspacePage } from "./BookWorkspacePage";
import { CompactToolbar } from "../components/layout/CompactToolbar";
import { OverflowMenu } from "../components/layout/OverflowMenu";
import { ReadingSettingsPopover } from "../components/layout/ReadingSettingsPopover";
import { WorkspaceViewSwitcher } from "../components/layout/WorkspaceViewSwitcher";
import { StartAnalysisDialog } from "../components/analysis/StartAnalysisDialog";
import { BoundaryReviewPanel } from "../components/analysis/BoundaryReviewPanel";
import { ConfirmBoundaryDivisionPanel } from "../components/analysis/ConfirmBoundaryDivisionPanel";
import { SceneBoundaryReviewPanel } from "../components/analysis/SceneBoundaryReviewPanel";
import { ReparseDialog } from "../components/books/ReparseDialog";
import { ChapterNavigatorDrawer } from "../components/books/ChapterNavigatorDrawer";
import {
  applyNavigateToChapterReading,
  bodyChapters,
  buildChapterReadingSearchParams,
} from "../services/chapterNavigation";
import { UnifiedAnalysisRecoveryCard } from "../components/chapterAnalysis/UnifiedAnalysisRecoveryCard";
import { ChapterAnalysisProgressPanel } from "../components/chapterAnalysis/ChapterAnalysisProgressPanel";
import { ReaderJourneyProgressCard } from "../components/chapterAnalysis/ReaderJourneyProgressCard";
import { EmbeddedAnalysisResultShell } from "../components/chapterResult/EmbeddedAnalysisResultShell";
import { WorkspaceJourneyPane } from "../components/readerJourney/WorkspaceJourneyPane";
import { ProNativeOverviewEntry } from "../components/proNativeOverview/ProNativeOverviewEntry";
import { StateView } from "../components/ui/StateView";
import { useCurrentPageAnalysisProgress } from "../hooks/useCurrentPageAnalysisProgress";
import { analysisApi } from "../services/analysisApi";
import { analysisRecoveryApi } from "../services/analysisRecoveryApi";
import { booksApi } from "../services/booksApi";
import { isConfirmOnlyBoundaryReview } from "../services/boundaryReviewMode";
import {
  getOrCreateJourneyClientRequestId,
  isAwaitingSceneBoundaryConfirmation,
  isChapterAnalysisComplete,
  isChapterAnalysisInFlight,
  isSceneAnalysisComplete,
  mapChapterCompositionState,
  resolveChapterWorkspaceView,
  type WorkspaceView,
} from "../services/chapterJourneyComposition";
import { resolveChapterPrimaryAction } from "../services/chapterPrimaryAction";
import {
  buildChapterAnalysisPresentationV1,
  type ChapterAnalysisPresentationV1,
} from "../services/chapterAnalysisPresentation";
import { resolveSceneJourneyGate } from "../services/resolveSceneJourneyGate";
import {
  formatJourneyElapsed,
  journeyElapsedMs,
  preserveJourneyRunInParams,
  resolveCurrentReaderJourney,
  type JourneyCandidate,
} from "../services/resolveCurrentReaderJourney";
import { mapReaderJourneyStatusToUi } from "../services/mapReaderJourneyStatusToUi";
import {
  chapterProgressHref,
  chapterResultHref,
  discoverActiveChapterRun,
} from "../services/discoverActiveChapterRun";
import { normalizeRunLifecycle } from "../services/runLifecycle";
import {
  resolveJourneyPageState,
  shouldPollJourneyResult,
  type JourneyPageView,
} from "../services/resolveJourneyPageState";
import {
  resolveWorkspaceLayout,
  type WorkspaceActiveTab,
} from "../services/resolveWorkspaceLayout";
import { useUiStore } from "../stores/uiStore";
import type { ReaderJourneyResult } from "../types";

type JourneyQueryPayload = ReaderJourneyResult & {
  __fetchSeq?: number;
  updated_at?: string | null;
  retryable?: boolean | null;
  error_code?: string | null;
  user_error_message?: string | null;
};

type ChapterView = WorkspaceView;

function parsePositiveInt(value: string | null): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function firstValidChapterId(
  chapters: { id: number; section_type: string }[] | null | undefined,
): number | null {
  if (!chapters?.length) return null;
  const first = chapters.find((item) => item.section_type === "chapter") || chapters[0];
  return first?.id ?? null;
}

function clickResults(selector: string) {
  document.querySelector<HTMLElement>(selector)?.dispatchEvent(
    new MouseEvent("click", { bubbles: true, cancelable: true }),
  );
  document.querySelector<HTMLButtonElement | HTMLAnchorElement>(selector)?.click();
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
  const [emptyDiagnostics, setEmptyDiagnostics] = useState<{
    encoding: string;
    candidate_count: number;
    final_chapter_count: number;
    warning?: string | null;
  } | null>(null);
  const [analysisInfoOpen, setAnalysisInfoOpen] = useState(false);
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [budgetModalOpen, setBudgetModalOpen] = useState(false);
  const [budgetModalRunId, setBudgetModalRunId] = useState<number | null>(null);
  /** In-memory only: survives polling, clears on full page refresh/remount. */
  const seenBudgetModalRef = useRef<Set<number>>(new Set());
  /** User-initiated shell view; prevents non-essential system redirects. */
  const userPinnedViewRef = useRef<ChapterView | null>(null);
  const userPinnedTabRef = useRef<WorkspaceActiveTab | null>(null);
  const qc = useQueryClient();
  const { contentWidth, showParagraphIds } = useUiStore();

  const analysisRunFromUrl = parsePositiveInt(searchParams.get("analysisRun"));
  const chapterFromUrl = parsePositiveInt(searchParams.get("chapter"));
  const journeyRunFromUrl = parsePositiveInt(searchParams.get("journeyRun"));

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

  const firstChapterId = useMemo(
    () => firstValidChapterId(chapters.data),
    [chapters.data],
  );
  const chaptersReady = !chapters.isLoading && !chapters.isError;
  const noChapters = chaptersReady && firstChapterId == null;
  /** /books/:id with no chapter → loading chapters or replace into first reading. */
  const bootstrappingChapter = chapterFromUrl == null && !noChapters;

  // Library Open (/books/:id): replace into first chapter reading workspace.
  useEffect(() => {
    if (chapterFromUrl != null) return;
    if (!chaptersReady || firstChapterId == null) return;
    setSearchParams(
      () => {
        const next = new URLSearchParams();
        next.set("chapter", String(firstChapterId));
        next.set("view", "reading");
        return next;
      },
      { replace: true },
    );
  }, [chapterFromUrl, chaptersReady, firstChapterId, setSearchParams]);

  const chapterId = chapterFromUrl;

  // Do not auto-write analysisRun into the URL. Library Open and chapter switches stay on
  // reading; historical/in-flight runs only surface when explicitly bound (deep link / start).

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
      setSearchParams(
        () => buildChapterReadingSearchParams(match.id),
        { replace: false },
      );
      userPinnedViewRef.current = "reading";
      userPinnedTabRef.current = "text";
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
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("chapter", String(runChapterId));
        next.set("analysisRun", String(analysisRunId));
        return next;
      },
      { replace: true },
    );
  }, [
    analysisRunId,
    progress.run,
    progress.run?.subject_id,
    chapterId,
    setSearchParams,
  ]);

  const sceneComplete = isSceneAnalysisComplete(progress.run);
  const journeyFetchSeqRef = useRef(0);
  const appliedJourneyMetaRef = useRef<{
    seq: number;
    updatedAt: string | null;
    journeyId: number | null;
  }>({ seq: 0, updatedAt: null, journeyId: null });
  const stableJourneyPageViewRef = useRef<JourneyPageView>("unknown");

  const journey = useQuery({
    queryKey: ["reader-journey", bookId, chapterId, analysisRunId, journeyRunFromUrl],
    queryFn: async (): Promise<JourneyQueryPayload> => {
      const seq = ++journeyFetchSeqRef.current;
      const data =
        journeyRunFromUrl != null
          ? await analysisApi.readerJourneyById(journeyRunFromUrl, {
              bookId,
              chapterId: chapterId!,
            })
          : await analysisApi.readerJourney(analysisRunId!, {
              bookId,
              chapterId: chapterId!,
            });
      return { ...(data as JourneyQueryPayload), __fetchSeq: seq };
    },
    enabled:
      Number.isFinite(bookId) &&
      !!chapterId &&
      (journeyRunFromUrl != null || !!analysisRunId),
    placeholderData: undefined,
    retry: false,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (
        shouldPollJourneyResult({
          journeyStatus: status,
          parentJourneyStatus: progress.run?.journey_status,
          effectiveStatus: progress.run?.effective_status,
          sceneComplete,
          pageView: stableJourneyPageViewRef.current,
        })
      ) {
        return 2000;
      }
      return false;
    },
  });
  const compositionUiState = mapChapterCompositionState(progress.run, journey.data);
  const awaitingSceneBoundaryConfirmation =
    compositionUiState === "awaiting_scene_boundary_confirmation" ||
    isAwaitingSceneBoundaryConfirmation(progress.run);
  const hasJourney = Boolean(
    journey.data?.status === "succeeded" && journey.data.visualization,
  );
  const chapterComplete =
    isChapterAnalysisComplete(progress.run) || compositionUiState === "succeeded";
  const awaitingRunHydration = Boolean(analysisRunId) && progress.isLoading && !progress.run;
  const chapterInFlight =
    awaitingRunHydration ||
    isChapterAnalysisInFlight(progress.run, compositionUiState) ||
    (Boolean(analysisRunId) &&
      !chapterComplete &&
      (searchParams.get("view") === "progress" || progress.uiState === "running"));

  const requestedView = searchParams.get("view");
  const requestedTab = searchParams.get("tab");
  const view = resolveChapterWorkspaceView({
    requestedView,
    userPinnedView: userPinnedViewRef.current,
    chapterComplete,
    inFlight: chapterInFlight,
    composition: compositionUiState,
  });

  const journeyScopeMismatch = Boolean(
    journey.isError &&
      String((journey.error as { message?: string } | null)?.message || "").includes(
        "ANALYSIS_RUN_SCOPE_MISMATCH",
      ),
  );
  const journeyExplicitMissing = Boolean(
    journeyRunFromUrl != null &&
      journey.isError &&
      ((journey.error as { status?: number } | null)?.status === 404 ||
        String((journey.error as { message?: string } | null)?.message || "").includes(
          "READER_JOURNEY_RUN_NOT_FOUND",
        )),
  );
  const journeyQueryStatus: "idle" | "loading" | "success" | "error" =
    !analysisRunId && journeyRunFromUrl == null
      ? "idle"
      : journey.isLoading || (journey.isFetching && !journey.data)
        ? "loading"
        : journey.isError
          ? "error"
          : journey.isSuccess
            ? "success"
            : "idle";

  const workspaceLayout = resolveWorkspaceLayout({
    requestedView,
    requestedTab,
    userPinnedTab: userPinnedTabRef.current,
    chapterComplete,
    inFlight: chapterInFlight,
    sceneAvailable: sceneComplete || chapterComplete,
    journeyAvailable: hasJourney,
    journeyStatus: journey.data?.status,
    journeyQueryStatus,
    journeyIntegrityStatus:
      (journey.data as { integrity_status?: string } | null | undefined)?.integrity_status ??
      (journey.data as { integrity?: { status?: string } } | null | undefined)?.integrity?.status,
    journeyTrusted: (journey.data as { trusted?: boolean } | null | undefined)?.trusted,
    scopeMismatch: journeyScopeMismatch,
  });
  const activeTab = workspaceLayout.activeTab;

  // Rewrite stale view=result bookmarks while Journey is still running (unless user pinned Scene).
  // Wait until the run row is loaded — never treat hydration as in-flight (would wipe deep-link tabs).
  useEffect(() => {
    if (!analysisRunId || !progress.run) return;
    if (requestedView !== "result") return;
    if (userPinnedViewRef.current === "result" || userPinnedTabRef.current === "scene") return;
    const stillRunning = isChapterAnalysisInFlight(progress.run, compositionUiState);
    if (!stillRunning) return;
    setSearchParams(
      (prev) => {
        if (prev.get("view") !== "result") return prev;
        const next = new URLSearchParams(prev);
        next.set("view", "progress");
        next.delete("tab");
        next.delete("mode");
        next.delete("scene");
        next.delete("resultTab");
        next.delete("journeyView");
        preserveJourneyRunInParams(next, journeyRunFromUrl ?? journeyRunId);
        return next;
      },
      { replace: true },
    );
  }, [analysisRunId, progress.run, compositionUiState, requestedView, setSearchParams]);

  const boundJourneyRunId =
    journeyRunFromUrl ??
    progress.run?.journey_run_id ??
    appliedJourneyMetaRef.current.journeyId ??
    journey.data?.journey_run_id ??
    null;
  const journeyRunId = boundJourneyRunId;

  const journeyPageView = useMemo((): JourneyPageView => {
    const data = journey.data as JourneyQueryPayload | undefined;
    const seq = data?.__fetchSeq ?? null;
    const responseJourneyId = data?.journey_run_id ?? null;
    const currentJourneyId =
      journeyRunFromUrl ??
      responseJourneyId ??
      progress.run?.journey_run_id ??
      appliedJourneyMetaRef.current.journeyId;
    const finalArtifactAvailable = Boolean(
      progress.run?.journey_result_available === true ||
        progress.run?.chapter_complete === true ||
        (data?.status === "succeeded" && data.visualization) ||
        hasJourney,
    );
    const resolved = resolveJourneyPageState({
      currentJourneyId,
      responseJourneyId,
      journeyStatus: data?.status,
      parentJourneyStatus:
        journeyRunFromUrl != null ? data?.status ?? null : progress.run?.journey_status,
      effectiveStatus:
        journeyRunFromUrl != null ? data?.status ?? null : progress.run?.effective_status,
      errorCode:
        (data as { error_code?: string } | undefined)?.error_code ??
        progress.run?.journey_error_code ??
        progress.run?.error_code ??
        null,
      retryable:
        (data as { retryable?: boolean } | undefined)?.retryable ??
        progress.run?.journey_retryable ??
        null,
      finalArtifactAvailable,
      chapterComplete:
        progress.run?.chapter_complete === true || compositionUiState === "succeeded",
      temporaryFetchError: Boolean(
        journey.isError &&
          !journeyScopeMismatch &&
          !String((journey.error as { message?: string } | null)?.message || "").includes(
            "ANALYSIS_RUN_SCOPE_MISMATCH",
          ),
      ),
      requestSequence: seq,
      appliedSequence: appliedJourneyMetaRef.current.seq || null,
      responseUpdatedAt: data?.updated_at ?? null,
      appliedUpdatedAt: appliedJourneyMetaRef.current.updatedAt,
    });
    if (resolved == null) {
      return stableJourneyPageViewRef.current;
    }
    // Successful / active / completed responses clear sticky failure view.
    stableJourneyPageViewRef.current = resolved;
    if (seq != null && (appliedJourneyMetaRef.current.seq === 0 || seq >= appliedJourneyMetaRef.current.seq)) {
      appliedJourneyMetaRef.current = {
        seq,
        updatedAt: data?.updated_at ?? appliedJourneyMetaRef.current.updatedAt,
        journeyId: responseJourneyId ?? appliedJourneyMetaRef.current.journeyId,
      };
    }
    return resolved;
  }, [
    journey.data,
    journey.isError,
    journey.error,
    journeyScopeMismatch,
    journeyRunFromUrl,
    progress.run,
    compositionUiState,
    hasJourney,
  ]);

  const journeyFailed = journeyPageView === "terminal_failed";
  const journeyInterrupted = journeyPageView === "interrupted";
  const journeyTemporaryError = journeyPageView === "temporary_error";
  const journeyActiveView =
    journeyPageView === "active" || compositionUiState === "reader_journey_processing";

  const journeyProgress = useQuery({
    queryKey: ["reader-journey-progress", journeyRunId],
    queryFn: () => analysisApi.readerJourneyProgress(journeyRunId!),
    enabled:
      !!journeyRunId &&
      (journeyActiveView || journeyFailed || journeyInterrupted || journeyTemporaryError),
    refetchInterval:
      journeyActiveView || journeyTemporaryError
        ? 2000
        : false,
  });

  // Progress status can refine the page view (e.g. fresher running counts) without
  // letting an older failed journey GET stick.
  const journeyPageViewWithProgress = useMemo((): JourneyPageView => {
    const progressStatus = journeyProgress.data?.status ?? null;
    if (!progressStatus) return journeyPageView;
    const data = journey.data as JourneyQueryPayload | undefined;
    const refined = resolveJourneyPageState({
      currentJourneyId:
        progress.run?.journey_run_id ??
        journeyProgress.data?.journey_run_id ??
        data?.journey_run_id,
      responseJourneyId: journeyProgress.data?.journey_run_id ?? data?.journey_run_id,
      journeyStatus: data?.status,
      progressStatus,
      parentJourneyStatus: progress.run?.journey_status,
      effectiveStatus: progress.run?.effective_status,
      errorCode:
        journeyProgress.data?.root_error_code ??
        (data as { error_code?: string } | undefined)?.error_code ??
        progress.run?.journey_error_code ??
        null,
      retryable:
        journeyProgress.data?.retryable ??
        (data as { retryable?: boolean } | undefined)?.retryable ??
        progress.run?.journey_retryable ??
        null,
      finalArtifactAvailable: Boolean(
        progress.run?.journey_result_available === true ||
          progress.run?.chapter_complete === true ||
          (data?.status === "succeeded" && data.visualization) ||
          hasJourney,
      ),
      chapterComplete:
        progress.run?.chapter_complete === true || compositionUiState === "succeeded",
      temporaryFetchError: journeyTemporaryError && journeyProgress.isError,
      requestSequence: data?.__fetchSeq ?? null,
      appliedSequence: appliedJourneyMetaRef.current.seq || null,
    });
    if (refined == null) return journeyPageView;
    stableJourneyPageViewRef.current = refined;
    return refined;
  }, [
    journeyPageView,
    journeyProgress.data,
    journeyProgress.isError,
    journey.data,
    progress.run,
    compositionUiState,
    hasJourney,
    journeyTemporaryError,
  ]);

  const showJourneyTerminalFailed = journeyPageViewWithProgress === "terminal_failed";
  const showJourneyInterrupted = journeyPageViewWithProgress === "interrupted";
  const showJourneyTemporaryError = journeyPageViewWithProgress === "temporary_error";
  // CHG-011: terminal/interrupted must never share the screen with running UI.
  const showJourneyActive =
    journeyPageViewWithProgress === "active" &&
    !showJourneyInterrupted &&
    !showJourneyTerminalFailed &&
    !showJourneyTemporaryError;
  const showJourneyAwaiting =
    !showJourneyTerminalFailed &&
    !showJourneyInterrupted &&
    !showJourneyTemporaryError &&
    !showJourneyActive &&
    !awaitingSceneBoundaryConfirmation &&
    compositionUiState === "awaiting_reader_journey_start";

  // CHG-018: drop stale recovery-plan cache as soon as journey is active.
  useEffect(() => {
    if (!showJourneyActive && compositionUiState !== "reader_journey_processing") return;
    const runId = analysisRunId ?? progress.run?.id;
    if (runId == null) return;
    void qc.invalidateQueries({ queryKey: ["analysis-recovery-plan", runId] });
  }, [
    showJourneyActive,
    compositionUiState,
    analysisRunId,
    progress.run?.id,
    qc,
  ]);

  const showJourneyResult =
    !showJourneyTerminalFailed &&
    !showJourneyInterrupted &&
    !showJourneyTemporaryError &&
    !showJourneyActive &&
    !showJourneyAwaiting &&
    !awaitingSceneBoundaryConfirmation;

  // After full chapter success from an in-flight pipeline, open Journey once.
  // Do not auto-open when landing on historical complete runs from book home / chapter pick.
  const prevCompositionRef = useRef(compositionUiState);
  const autoOpenedJourneyRef = useRef<number | null>(null);
  useEffect(() => {
    const prev = prevCompositionRef.current;
    prevCompositionRef.current = compositionUiState;
    if (!hasJourney || !analysisRunId) return;
    if (!chapterComplete || compositionUiState !== "succeeded") return;
    if (userPinnedViewRef.current === "reading") return;
    if (userPinnedViewRef.current === "result" && searchParams.get("tab") !== "reader-journey") {
      return;
    }
    const transitionedFromJourney =
      prev === "reader_journey_processing" || prev === "awaiting_reader_journey_start";
    if (!transitionedFromJourney) return;
    if (autoOpenedJourneyRef.current === analysisRunId) return;
    autoOpenedJourneyRef.current = analysisRunId;
    userPinnedViewRef.current = null;
    setSearchParams(
      (params) => {
        const next = new URLSearchParams(params);
        next.set("view", "result");
        next.set("tab", "reader-journey");
        next.set("analysisRun", String(analysisRunId));
        preserveJourneyRunInParams(next, journeyRunFromUrl ?? journeyRunId);
        return next;
      },
      { replace: true },
    );
  }, [
    hasJourney,
    compositionUiState,
    chapterComplete,
    analysisRunId,
    setSearchParams,
    searchParams,
  ]);

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
  const discoveredChapterRun = useMemo(
    () => (analysisRunId ? null : discoverActiveChapterRun(runs, chapterId)),
    [analysisRunId, runs, chapterId],
  );
  const lifecycleChapterRun = progress.run ?? discoveredChapterRun;
  const sceneBoundaryReviewActive =
    awaitingSceneBoundaryConfirmation ||
    isAwaitingSceneBoundaryConfirmation(lifecycleChapterRun);
  const latestSucceeded = runs.find(
    (run) =>
      run.status === "succeeded" && chapterId && String(run.subject_id) === String(chapterId),
  );

  const showProgressPanel =
    workspaceLayout.showProgressContext &&
    Boolean(analysisRunId) &&
    !panelCollapsed;
  const showRunningBanner =
    view === "reading" &&
    Boolean(analysisRunId) &&
    (progress.uiState === "running" ||
      progress.uiState === "boundary_review_required" ||
      progress.uiState === "awaiting_budget_adjustment" ||
      progress.uiState === "provider_recovery" ||
      compositionUiState === "reader_journey_processing" ||
      compositionUiState === "awaiting_reader_journey_start");
  const showCompleteBanner =
    view === "reading" && Boolean(analysisRunId) && chapterComplete;
  const showSceneCompleteBanner =
    view === "reading" &&
    Boolean(analysisRunId) &&
    compositionUiState === "awaiting_reader_journey_start" &&
    !awaitingSceneBoundaryConfirmation;
  const showJourneyProcessingBanner =
    view === "reading" &&
    Boolean(analysisRunId) &&
    compositionUiState === "reader_journey_processing";

  useEffect(() => {
    if (progress.uiState === "boundary_review_required" && analysisRunId) {
      setReviewOpen(true);
      setPanelCollapsed(false);
    }
  }, [progress.uiState, analysisRunId]);

  // CHG-041: do not auto-mount scene boundary editor onto reader-journey / reviewOpen.
  // Entry is via view=scene-boundary-review (toolbar CTA / journey gate).

  useEffect(() => {
    if (progress.uiState !== "awaiting_budget_adjustment" || !progress.run) return;
    const runId = progress.run.id;
    if (seenBudgetModalRef.current.has(runId)) return;
    seenBudgetModalRef.current.add(runId);
    setBudgetModalRunId(runId);
    setBudgetModalOpen(true);
  }, [progress.uiState, progress.run]);

  const setView = (next: ChapterView, source: "user" | "system" = "user") => {
    if (source === "user") {
      userPinnedViewRef.current = next;
      userPinnedTabRef.current = next === "reading" || next === "progress" ? "text" : "scene";
    }
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("view", next);
        if (analysisRunId) params.set("analysisRun", String(analysisRunId));
        if (chapterId) params.set("chapter", String(chapterId));
        preserveJourneyRunInParams(params, journeyRunFromUrl ?? journeyRunId);
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

  const setResultTab = (tab: "analysis" | "journey", source: "user" | "system" = "user") => {
    if (source === "user") {
      userPinnedViewRef.current = "result";
      userPinnedTabRef.current = tab === "journey" ? "journey" : "scene";
    }
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("view", "result");
        if (analysisRunId) params.set("analysisRun", String(analysisRunId));
        if (chapterId) params.set("chapter", String(chapterId));
        preserveJourneyRunInParams(params, journeyRunFromUrl ?? journeyRunId);
        if (tab === "journey") {
          params.set("tab", "reader-journey");
        } else {
          params.delete("tab");
          params.delete("mode");
          params.delete("scene");
          params.delete("paragraph");
          params.delete("metric");
          params.delete("cluster");
        }
        return params;
      },
      { replace: true },
    );
  };

  const bindAnalysisRun = (
    runId: number,
    meta?: { existing?: boolean; status?: string; taskType?: string },
  ) => {
    setPanelCollapsed(false);
    const phase = normalizeRunLifecycle({
      status: meta?.status || "scene_analysis_running",
      task_type: meta?.taskType || "scene_pipeline",
      subject_type: "chapter",
      chapter_complete: meta?.status === "succeeded",
    } as any);
    const view =
      phase === "completed" ? "result" : "progress";
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("analysisRun", String(runId));
        next.set("view", view);
        if (chapterId) next.set("chapter", String(chapterId));
        return next;
      },
      { replace: true },
    );
  };

  const selectChapterFromCatalog = (id: number) => {
    setCatalogOpen(false);
    userPinnedViewRef.current = "reading";
    userPinnedTabRef.current = "text";
    applyNavigateToChapterReading(setSearchParams, id);
    // Reading pane scrollTop resets after new chapter body commits in BookWorkspacePage.
  };

  const openCatalogOrFocusNav = () => {
    setCatalogOpen(true);
  };

  useEffect(() => {
    if (!catalogOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setCatalogOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [catalogOpen]);

  useEffect(() => {
    if (catalogOpen || dialog || reparseOpen || chapterInfoOpen || budgetModalOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (!event.altKey || event.shiftKey || event.ctrlKey || event.metaKey) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return;
      }
      const body = bodyChapters(chapters.data);
      if (!chapterId || !body.length) return;
      const idx = body.findIndex((c) => c.id === chapterId);
      if (idx < 0) return;
      const next =
        event.key === "ArrowLeft"
          ? idx > 0
            ? body[idx - 1]
            : null
          : idx < body.length - 1
            ? body[idx + 1]
            : null;
      if (!next) return;
      event.preventDefault();
      setCatalogOpen(false);
      userPinnedViewRef.current = "reading";
      userPinnedTabRef.current = "text";
      applyNavigateToChapterReading(setSearchParams, next.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    catalogOpen,
    dialog,
    reparseOpen,
    chapterInfoOpen,
    budgetModalOpen,
    chapters.data,
    chapterId,
    setSearchParams,
  ]);

  const bookTitle = book.data?.title || "书籍";

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
              clickResults('[data-testid="journey-export-png"]');
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
            label: "确认场景划分",
            group: "操作",
            testId: "book-more-boundary-review",
            onSelect: () => {
              if (sceneBoundaryReviewActive) openSceneBoundaryReview();
              else setReviewOpen(true);
            },
          },
        ]
      : [
          ...(hasJourney
            ? [
                {
                  id: "reader-journey-view",
                  label: "查看读者旅程",
                  group: "查看",
                  testId: "book-more-reader-journey-view",
                  onSelect: () => {
                    if (analysisRunId) {
                      setResultTab("journey", "user");
                      return;
                    }
                    if (latestSucceeded) {
                      navigate(
                        `/analysis-runs/${latestSucceeded.id}/results?tab=reader-journey`,
                      );
                    }
                  },
                },
              ]
            : []),
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
            label: "确认场景划分",
            group: "查看",
            testId: "book-more-boundary-review",
            onSelect: () => {
              if (sceneBoundaryReviewActive) openSceneBoundaryReview();
              else setReviewOpen(true);
            },
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

  const sceneBoundaryReviewView = searchParams.get("view") === "scene-boundary-review";

  const sceneBoundariesQuery = useQuery({
    queryKey: ["scene-boundaries", chapterId],
    queryFn: () => analysisApi.sceneBoundariesOverview(chapterId!),
    enabled: Boolean(chapterId) && (Boolean(analysisRunId) || sceneBoundaryReviewView),
    retry: false,
  });

  const journeyCandidates: JourneyCandidate[] = [];
  if (journey.data?.journey_run_id != null) {
    journeyCandidates.push({
      id: journey.data.journey_run_id,
      status: String(journey.data.status || ""),
      scene_revision_id:
        (journey.data as { scene_revision_id?: number }).scene_revision_id ?? null,
      result_status:
        (journey.data as { result_status?: string }).result_status ?? null,
      started_at: (journey.data as { started_at?: string }).started_at ?? null,
      created_at: (journey.data as { created_at?: string }).created_at ?? null,
      updated_at: journey.data.updated_at ?? null,
      completed_at: (journey.data as { completed_at?: string }).completed_at ?? null,
      retryable: (journey.data as { retryable?: boolean }).retryable ?? null,
      root_error_code: (journey.data as { error_code?: string }).error_code ?? null,
      total_scene_count:
        (journey.data as { total_scene_count?: number }).total_scene_count ?? null,
      completed_scene_count:
        (journey.data as { completed_scene_count?: number }).completed_scene_count ?? null,
    });
  }
  if (
    progress.run?.journey_run_id != null &&
    !journeyCandidates.some((item) => item.id === progress.run?.journey_run_id)
  ) {
    journeyCandidates.push({
      id: progress.run.journey_run_id,
      status: String(progress.run.journey_status || progress.run.effective_status || ""),
      scene_revision_id: null,
      started_at: progress.run.started_at ?? null,
    });
  }
  const resolvedCurrentJourney = resolveCurrentReaderJourney({
    explicitJourneyRunId: journeyRunFromUrl,
    confirmedRevisionId: sceneBoundariesQuery.data?.confirmed_revision?.revision_id,
    candidates: journeyCandidates,
  });
  const selectedJourneyRunId = resolvedCurrentJourney.journey?.id ?? journeyRunId;
  const selectedJourneyElapsedMs = journeyElapsedMs({
    journey: resolvedCurrentJourney.journey,
  });
  const journeySidebarUi = mapReaderJourneyStatusToUi({
    journeyStatus: resolvedCurrentJourney.journey?.status,
    resultStatus: resolvedCurrentJourney.journey?.result_status,
    retryable: resolvedCurrentJourney.journey?.retryable,
  });

  // Keep journeyRun in the URL once we know the selected run (refresh / tab safe).
  useEffect(() => {
    if (!selectedJourneyRunId) return;
    if (journeyRunFromUrl === selectedJourneyRunId) return;
    if (searchParams.get("tab") !== "reader-journey" && searchParams.get("view") !== "result") {
      return;
    }
    setSearchParams(
      (prev) => {
        if (prev.get("journeyRun") === String(selectedJourneyRunId)) return prev;
        const next = new URLSearchParams(prev);
        preserveJourneyRunInParams(next, selectedJourneyRunId);
        return next;
      },
      { replace: true },
    );
  }, [
    selectedJourneyRunId,
    journeyRunFromUrl,
    searchParams,
    setSearchParams,
  ]);

  const sceneBoundaryEntry =
    sceneBoundariesQuery.data?.draft_revision != null
      ? ("continue_draft" as const)
      : sceneBoundaryReviewActive
        ? ("confirm" as const)
        : sceneBoundariesQuery.data?.confirmed_revision != null
          ? ("readjust" as const)
          : ("confirm" as const);

  const openSceneBoundaryReview = () => {
    if (!chapterId) return;
    userPinnedViewRef.current = "result";
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("view", "scene-boundary-review");
        params.set("chapter", String(chapterId));
        if (analysisRunId) params.set("analysisRun", String(analysisRunId));
        else if (lifecycleChapterRun?.id) {
          params.set("analysisRun", String(lifecycleChapterRun.id));
        }
        preserveJourneyRunInParams(params, journeyRunFromUrl ?? journeyRunId);
        params.delete("tab");
        params.delete("mode");
        params.delete("scene");
        params.delete("paragraph");
        params.delete("metric");
        params.delete("cluster");
        params.delete("resultTab");
        return params;
      },
      { replace: false },
    );
    setPanelCollapsed(false);
  };

  const chapterPresentation: ChapterAnalysisPresentationV1 = useMemo(
    () =>
      buildChapterAnalysisPresentationV1({
        chapterId: chapterId ?? null,
        analysisRunId,
        journeyRunId: selectedJourneyRunId ?? journeyRunId,
        confirmedRevisionId:
          sceneBoundariesQuery.data?.confirmed_revision?.revision_id ?? null,
        confirmedSceneCount:
          sceneBoundariesQuery.data?.confirmed_revision?.scenes?.length ?? null,
        composition: compositionUiState,
        pageView: journeyPageViewWithProgress,
        lifecycleRun: progress.run ?? lifecycleChapterRun,
        completedSceneCount: progress.run?.completed_scene_count ?? null,
        totalSceneCount:
          progress.run?.total_scene_count ??
          sceneBoundariesQuery.data?.confirmed_revision?.scenes?.length ??
          null,
        canResumeJourney: Boolean(
          progress.run?.journey_retryable === true ||
            journeyProgress.data?.retryable === true,
        ),
        chapterComplete,
        awaitingConfirmation: awaitingSceneBoundaryConfirmation,
        inFlight: chapterInFlight,
        journeyStatus:
          journeyProgress.data?.status ||
          journey.data?.status ||
          progress.run?.journey_status ||
          null,
        statusVersion: progress.run?.status_version ?? lifecycleChapterRun?.status_version ?? null,
        hasActiveTask:
          showJourneyActive ||
          compositionUiState === "reader_journey_processing",
        hasCheckpointOrRecoveryBasis: Boolean(
          progress.run?.journey_retryable === true ||
            journeyProgress.data?.retryable === true,
        ),
      }),
    [
      chapterId,
      analysisRunId,
      selectedJourneyRunId,
      journeyRunId,
      sceneBoundariesQuery.data,
      compositionUiState,
      journeyPageViewWithProgress,
      progress.run,
      lifecycleChapterRun,
      journeyProgress.data?.retryable,
      journeyProgress.data?.status,
      journey.data?.status,
      chapterComplete,
      awaitingSceneBoundaryConfirmation,
      chapterInFlight,
      showJourneyActive,
    ],
  );

  const journeyNavInProgress =
    chapterPresentation.workflow_state === "journey_starting" ||
    chapterPresentation.workflow_state === "journey_running" ||
    chapterPresentation.workflow_state === "journey_interrupted";
  // CHG-017: never use historical hasJourney to advertise ordinary journey nav.
  const journeyNavAvailable = chapterPresentation.show_journey_nav;

  useEffect(() => {
    // Wait for AnalysisRun hydrate — otherwise inFlight fallback falsely redirects
    // succeeded journey deep links to progress.
    if (awaitingRunHydration) return;
    if (analysisRunId && progress.isLoading && !progress.run && !lifecycleChapterRun) return;

    const onJourneyDeepLink =
      activeTab === "journey" ||
      searchParams.get("tab") === "reader-journey" ||
      (searchParams.get("view") === "result" &&
        (searchParams.get("tab") === "reader-journey" || searchParams.get("resultTab") === "reader-journey"));
    if (!onJourneyDeepLink) return;

    // CHG-017: awaiting confirmation → scene confirm page (not「尚未开始」gate).
    if (chapterPresentation.redirect_journey_to_confirm) {
      if (sceneBoundaryReviewView) return;
      if (
        compositionUiState === "reader_journey_processing" ||
        compositionUiState === "awaiting_reader_journey_start"
      ) {
        return;
      }
      openSceneBoundaryReview();
      return;
    }

    // CHG-017: boundary / scene analysis / waiting scenes → progress page.
    if (!chapterPresentation.redirect_journey_to_progress) return;
    if (searchParams.get("view") === "progress" && searchParams.get("tab") !== "reader-journey") {
      return;
    }
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("view", "progress");
        if (analysisRunId) params.set("analysisRun", String(analysisRunId));
        else if (lifecycleChapterRun?.id) {
          params.set("analysisRun", String(lifecycleChapterRun.id));
        }
        if (chapterId) params.set("chapter", String(chapterId));
        params.delete("tab");
        params.delete("resultTab");
        params.delete("mode");
        params.delete("scene");
        return params;
      },
      { replace: true },
    );
    userPinnedTabRef.current = null;
    userPinnedViewRef.current = null;
  }, [
    awaitingRunHydration,
    progress.isLoading,
    progress.run,
    chapterPresentation.redirect_journey_to_confirm,
    chapterPresentation.redirect_journey_to_progress,
    chapterPresentation.workflow_state,
    activeTab,
    sceneBoundaryReviewView,
    chapterId,
    analysisRunId,
    lifecycleChapterRun,
    compositionUiState,
    searchParams,
  ]);

  const resumeJourneyAnalysis = () => {
    void (async () => {
      const requestRunId = analysisRunId ?? progress.run?.id;
      if (requestRunId == null) return;
      try {
        if (selectedJourneyRunId ?? journeyRunId) {
          await analysisApi.resumeReaderJourney((selectedJourneyRunId ?? journeyRunId)!, {
            client_request_id: getOrCreateJourneyClientRequestId(requestRunId),
            cloud_consent: true,
            confirmed: true,
          });
        } else if (progress.run) {
          await analysisRecoveryApi.recover(progress.run.id, {
            client_request_id: getOrCreateJourneyClientRequestId(requestRunId),
            cloud_consent: true,
            confirmed: true,
            recovery_mode: "unified",
            resume: true,
          });
        }
      } finally {
        stableJourneyPageViewRef.current = "unknown";
        appliedJourneyMetaRef.current = {
          seq: 0,
          updatedAt: null,
          journeyId: selectedJourneyRunId ?? journeyRunId,
        };
        void qc.invalidateQueries({ queryKey: ["reader-journey"] });
        void journey.refetch();
        void progress.refresh();
      }
    })();
  };

  const primaryAction = resolveChapterPrimaryAction({
    hasChapter: Boolean(chapterId) && !noChapters && !bootstrappingChapter,
    run: progress.run,
    composition: compositionUiState,
    chapterComplete,
    inFlight: chapterInFlight,
    lifecycleRun: lifecycleChapterRun,
    sceneBoundaryEntry:
      awaitingSceneBoundaryConfirmation || sceneBoundaryReviewActive
        ? sceneBoundaryEntry
        : undefined,
  });

  const effectivePrimaryAction =
    chapterPresentation.primary_action === "continue_analysis"
      ? { kind: "continue" as const, label: "继续分析", testId: "shell-continue-analysis" }
      : chapterPresentation.primary_action === "view_progress"
        ? {
            kind: "progress" as const,
            label: "查看分析进度",
            testId: "shell-view-analysis-progress",
          }
        : chapterPresentation.primary_action === "confirm_scenes"
          ? primaryAction.kind === "confirm"
            ? primaryAction
            : {
                kind: "confirm" as const,
                label: "确认场景",
                testId: "shell-continue-boundary-confirm",
              }
          : chapterPresentation.primary_action === "view_results"
            ? {
                kind: "result" as const,
                label: "查看分析结果",
                testId: "shell-view-analysis-result",
              }
            : primaryAction;

  const onPrimaryAction = () => {
    if (effectivePrimaryAction.kind === "start" || effectivePrimaryAction.kind === "reanalyze") {
      setDialog(true);
      return;
    }
    if (effectivePrimaryAction.kind === "continue") {
      resumeJourneyAnalysis();
      return;
    }
    const targetRun = lifecycleChapterRun;
    if (!targetRun || !chapterId) return;
    if (effectivePrimaryAction.kind === "confirm") {
      if (sceneBoundaryReviewActive || awaitingSceneBoundaryConfirmation) {
        openSceneBoundaryReview();
        return;
      }
      setReviewOpen(true);
      setPanelCollapsed(false);
      return;
    }
    if (effectivePrimaryAction.kind === "progress") {
      // Bind URL only on click — do not auto-rewrite reading URL on load.
      setSearchParams(
        () => {
          const params = new URLSearchParams(
            chapterProgressHref({
              bookId,
              chapterId,
              analysisRunId: targetRun.id,
            }).split("?")[1] || "",
          );
          return params;
        },
        { replace: false },
      );
      setPanelCollapsed(false);
      return;
    }
    if (effectivePrimaryAction.kind === "result") {
      setSearchParams(
        () => {
          const params = new URLSearchParams(
            chapterResultHref({
              bookId,
              chapterId,
              analysisRunId: targetRun.id,
            }).split("?")[1] || "",
          );
          return params;
        },
        { replace: false },
      );
    }
  };

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
        onClick={openCatalogOrFocusNav}
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
        onClick={openCatalogOrFocusNav}
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
      data-view={noChapters ? "empty" : bootstrappingChapter ? "bootstrapping" : workspaceLayout.shellView}
      data-active-tab={noChapters || bootstrappingChapter ? "text" : activeTab}
      data-book-home="false"
      data-catalog-open={catalogOpen ? "true" : "false"}
      data-has-progress={showProgressPanel ? "true" : "false"}
    >
      <CompactToolbar
        className="workspace-toolbar"
        data-testid="book-shell-toolbar"
        title={
          view === "result" && !noChapters && !bootstrappingChapter ? (
            resultToolbarTitle
          ) : (
            readingToolbarTitle
          )
        }
        primary={
          noChapters || bootstrappingChapter || effectivePrimaryAction.kind === "none" ? null : (
            <button
              type="button"
              className="primary"
              data-testid={effectivePrimaryAction.testId}
              disabled={
                (effectivePrimaryAction.kind === "start" ||
                  effectivePrimaryAction.kind === "reanalyze") &&
                startAnalysisDisabled
              }
              onClick={onPrimaryAction}
            >
              {effectivePrimaryAction.label}
            </button>
          )
        }
        secondary={
          <>
            {!noChapters && !bootstrappingChapter && view !== "result" ? (
              <ReadingSettingsPopover />
            ) : null}
            {!noChapters && !bootstrappingChapter ? (
              <ProNativeOverviewEntry bookId={bookId} />
            ) : null}
            {!noChapters &&
            !bootstrappingChapter &&
            (chapterInFlight ||
              chapterComplete ||
              sceneComplete ||
              view === "progress" ||
              view === "result") ? (
              <WorkspaceViewSwitcher
                active={
                  activeTab === "journey" ? "journey" : activeTab === "scene" ? "analysis" : "reading"
                }
                showAnalysisTab={false}
                showJourneyTab={chapterPresentation.show_journey_nav}
                journeyAvailable={journeyNavAvailable}
                journeyInProgress={journeyNavInProgress}
                onChange={(tab) => {
                  if (tab === "reading") {
                    setView("reading", "user");
                    return;
                  }
                  if (tab === "analysis") {
                    setResultTab("analysis", "user");
                    return;
                  }
                  setResultTab("journey", "user");
                }}
              />
            ) : null}
            {!noChapters && !bootstrappingChapter && panelCollapsed && analysisRunId ? (
              <button
                type="button"
                className="secondary"
                data-testid="chapter-analysis-expand"
                onClick={() => {
                  setPanelCollapsed(false);
                  setView("progress", "user");
                }}
              >
                展开分析面板
              </button>
            ) : null}
          </>
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
          className="book-shell-running-banner"
          data-testid="chapter-analysis-scene-complete-banner"
        >
          <span>场景分析已完成 · 正在衔接阅读旅程</span>
          <button
            type="button"
            data-testid="banner-continue-reader-journey"
            onClick={() => setResultTab("analysis", "user")}
          >
            查看场景分析
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

      {sceneBoundaryReviewView && chapterId && !noChapters && !bootstrappingChapter ? (
        <div className="shell-review-focus" data-testid="shell-scene-boundary-review">
          <SceneBoundaryReviewPanel
            chapterId={chapterId}
            chapterTitle={chapterTitle}
            analysisRunId={analysisRunId}
            journeyRunning={compositionUiState === "reader_journey_processing"}
            journeyRevisionId={
              (journey.data as { scene_revision_id?: number } | null | undefined)
                ?.scene_revision_id ?? null
            }
            onExit={() => setView("reading", "user")}
            onConfirmed={({ journeyStarted, journeyRunId: confirmedJourneyRunId }) => {
              void qc.invalidateQueries({ queryKey: ["reader-journey"] });
              void qc.invalidateQueries({ queryKey: ["scene-boundaries", chapterId] });
              void journey.refetch();
              void progress.refresh();
              // Always route with journeyRun when API returned an id (even if start
              // failed after queueing) so Reader Journey never falls back to analysisRun.
              if (journeyStarted || confirmedJourneyRunId) {
                setSearchParams(
                  (prev) => {
                    const params = new URLSearchParams(prev);
                    params.set("view", "result");
                    params.set("tab", "reader-journey");
                    if (chapterId) params.set("chapter", String(chapterId));
                    if (analysisRunId) params.set("analysisRun", String(analysisRunId));
                    if (confirmedJourneyRunId) {
                      params.set("journeyRun", String(confirmedJourneyRunId));
                    }
                    return params;
                  },
                  { replace: false },
                );
                userPinnedViewRef.current = "result";
                userPinnedTabRef.current = "journey";
              }
            }}
          />
        </div>
      ) : reviewOpen && chapterId && !noChapters && !bootstrappingChapter ? (
        <div className="shell-review-focus" data-testid="shell-boundary-review">
          {isConfirmOnlyBoundaryReview() ? (
            <ConfirmBoundaryDivisionPanel
              bookId={bookId}
              chapterId={chapterId}
              chapterTitle={chapterTitle}
              onExit={() => {
                setReviewOpen(false);
                void progress.refresh();
              }}
              onReidentify={() => {
                setReviewOpen(false);
                setDialog(true);
              }}
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
          ) : (
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
          )}
        </div>
      ) : (
        <div
          className="book-shell-body"
          data-has-progress={showProgressPanel ? "true" : "false"}
          data-view={workspaceLayout.shellView}
          data-active-tab={activeTab}
          data-workspace-mode={workspaceLayout.workspaceMode}
          data-testid="book-shell-body"
          data-workspace-root="true"
        >
          <div className="book-shell-main" data-testid="main-content-pane">
            {noChapters ? (
              <div className="book-shell-empty-chapters" data-testid="book-no-chapters-wrap">
                <StateView
                  kind="empty"
                  data-testid="book-no-chapters"
                  title="尚未识别到章节"
                  description="请重新识别章节，或查看导入诊断后再试。"
                  primaryAction={{
                    label: "重新识别章节",
                    testId: "book-no-chapters-reparse",
                    onClick: () => setReparseOpen(true),
                  }}
                  secondaryAction={{
                    label: "查看导入诊断",
                    testId: "book-no-chapters-diagnostics",
                    onClick: () => {
                      void booksApi.diagnostics(bookId).then((d) => setEmptyDiagnostics(d));
                    },
                  }}
                />
                {emptyDiagnostics ? (
                  <div className="notice workspace-diagnostics" data-testid="book-no-chapters-diag">
                    <b>识别结果</b>
                    <span>编码 {emptyDiagnostics.encoding}</span>
                    <span>
                      候选 {emptyDiagnostics.candidate_count} · 最终{" "}
                      {emptyDiagnostics.final_chapter_count}章
                    </span>
                    {emptyDiagnostics.warning ? <span>{emptyDiagnostics.warning}</span> : null}
                  </div>
                ) : null}
                <button
                  type="button"
                  className="secondary"
                  data-testid="book-no-chapters-back"
                  onClick={() => navigate("/library")}
                >
                  返回书库
                </button>
              </div>
            ) : null}

            {bootstrappingChapter ? (
              <StateView
                kind="loading"
                data-testid="book-chapter-bootstrap"
                title="正在打开正文…"
              />
            ) : null}

            {!noChapters && !bootstrappingChapter && activeTab === "text" ? (
              <div
                className="book-shell-workspace"
                data-testid="reading-workspace-body"
              >
                <BookWorkspacePage />
              </div>
            ) : null}

            {!noChapters && !bootstrappingChapter && activeTab === "scene" && analysisRunId ? (
              <EmbeddedAnalysisResultShell
                runId={analysisRunId}
                onReading={() => setView("reading", "user")}
              />
            ) : null}

            {!noChapters && !bootstrappingChapter && activeTab === "journey" && analysisRunId ? (
              <>
                {showJourneyTemporaryError ? (
                  <StateView
                    kind="loading"
                    data-testid="journey-temporary-error"
                    title="暂时无法读取最新进度"
                    description="正在重新连接，已完成的场景分析不会受到影响。"
                  />
                ) : null}
                {showJourneyTerminalFailed ? (
                  <StateView
                    kind="error"
                    data-testid="journey-failed"
                    title="阅读旅程生成失败"
                    description="已完成的场景分析不会受到影响。"
                    primaryAction={{
                      label: "重新生成阅读旅程",
                      testId: "journey-failed-retry",
                      onClick: () => {
                        void (async () => {
                          try {
                            if (selectedJourneyRunId ?? journeyRunId) {
                              await analysisApi.resumeReaderJourney(
                                (selectedJourneyRunId ?? journeyRunId)!,
                                {
                                  client_request_id: getOrCreateJourneyClientRequestId(
                                    analysisRunId ?? progress.run!.id,
                                  ),
                                  cloud_consent: true,
                                  confirmed: true,
                                },
                              );
                            } else if (progress.run) {
                              await analysisRecoveryApi.recover(progress.run.id, {
                                client_request_id: getOrCreateJourneyClientRequestId(progress.run.id),
                                cloud_consent: true,
                                confirmed: true,
                                recovery_mode: "unified",
                                resume: true,
                              });
                            }
                          } finally {
                            stableJourneyPageViewRef.current = "unknown";
                            appliedJourneyMetaRef.current = {
                              seq: 0,
                              updatedAt: null,
                              journeyId: selectedJourneyRunId ?? journeyRunId,
                            };
                            void qc.invalidateQueries({
                              queryKey: ["reader-journey"],
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
                {showJourneyInterrupted ? (
                  <StateView
                    kind="error"
                    data-testid="journey-interrupted"
                    title="阅读旅程已中断"
                    description="当前进度已保存，可以继续分析。Scene 分析已完成；阅读旅程尚未完成；当前任务可以继续。"
                    primaryAction={{
                      label: "继续分析",
                      testId: "journey-interrupted-continue",
                      onClick: resumeJourneyAnalysis,
                    }}
                    secondaryAction={{
                      label: "查看详情",
                      testId: "journey-interrupted-task-details",
                      onClick: () => navigate(`/tasks?run_id=${analysisRunId}`),
                    }}
                  />
                ) : null}
                {showJourneyAwaiting &&
                progress.run &&
                !showJourneyActive &&
                chapterPresentation.show_recovery_card ? (
                  <UnifiedAnalysisRecoveryCard
                    run={progress.run}
                    variant="card"
                    journeyStatus={
                      journeyProgress.data?.status ||
                      journey.data?.status ||
                      progress.run.journey_status ||
                      null
                    }
                    journeyPageActive={false}
                    journeyRunId={selectedJourneyRunId ?? journeyRunId}
                    confirmedRevisionId={
                      sceneBoundariesQuery.data?.confirmed_revision?.revision_id ?? null
                    }
                    canResume={chapterPresentation.can_resume}
                    workflowState={chapterPresentation.workflow_state}
                    onContinued={() => {
                      void qc.invalidateQueries({ queryKey: ["reader-journey"] });
                      void qc.invalidateQueries({
                        queryKey: ["analysis-recovery-plan"],
                      });
                      void journey.refetch();
                      void progress.refresh();
                    }}
                  />
                ) : null}
                {(() => {
                  const confirmed = sceneBoundariesQuery.data?.confirmed_revision;
                  const selected = resolvedCurrentJourney.journey;
                  const gate = resolveSceneJourneyGate({
                    awaitingConfirmation: Boolean(
                      sceneBoundariesQuery.data?.awaiting_confirmation ??
                        awaitingSceneBoundaryConfirmation,
                    ),
                    confirmedRevisionId: confirmed?.revision_id,
                    confirmedSource: confirmed?.source,
                    journeyStatus: selected?.status ?? journey.data?.status,
                    journeySceneRevisionId:
                      selected?.scene_revision_id ??
                      (journey.data as { scene_revision_id?: number } | null | undefined)
                        ?.scene_revision_id ??
                      null,
                    journeyResultStatus:
                      selected?.result_status ??
                      (journey.data as { result_status?: string } | null | undefined)
                        ?.result_status ??
                      null,
                  });
                  // Gate is only for empty / need-confirm / stale. Selected journey
                  // CHG-017: do not render「阅读旅程尚未开始」/ confirmed_no_journey
                  // intermediate pages — deep links redirect instead.
                  const showGate =
                    activeTab === "journey" &&
                    resolvedCurrentJourney.source === "none" &&
                    !showJourneyTemporaryError &&
                    !showJourneyInterrupted &&
                    !showJourneyTerminalFailed &&
                    !showJourneyActive &&
                    !showJourneyAwaiting &&
                    !awaitingSceneBoundaryConfirmation &&
                    !chapterPresentation.redirect_journey_to_confirm &&
                    !chapterPresentation.redirect_journey_to_progress &&
                    gate.kind === "stale_journey";
                  if (!showGate) return null;
                  return (
                    <StateView
                      kind="empty"
                      data-testid="reader-journey-stale-revision"
                      title={gate.title}
                      description={gate.description}
                      primaryAction={{
                        label: gate.primaryLabel,
                        testId: gate.primaryTestId,
                        onClick: () => openSceneBoundaryReview(),
                      }}
                    />
                  );
                })()}
                {showJourneyActive ? (
                  <ReaderJourneyProgressCard
                    analysisRunId={analysisRunId}
                    progress={journeyProgress.data}
                    loading={journeyProgress.isLoading && !journeyProgress.data}
                    errorMessage={
                      showJourneyTemporaryError
                        ? "暂时无法读取最新进度"
                        : journeyProgress.data?.user_error_message ||
                          journeyProgress.data?.root_error_message ||
                          null
                    }
                    onViewTaskDetails={() => navigate(`/tasks?run_id=${analysisRunId}`)}
                  />
                ) : null}
                {showJourneyResult ? (
                  <>
                    {journeyExplicitMissing ? (
                      <div
                        className="workspace-journey-pane state"
                        data-testid="reader-journey-explicit-missing"
                      >
                        <strong>指定的阅读旅程不存在或已被删除</strong>
                        <button type="button" className="secondary" onClick={() => setView("reading", "user")}>
                          返回正文阅读
                        </button>
                      </div>
                    ) : null}
                    {!journeyExplicitMissing &&
                    journeyRunFromUrl != null &&
                    (journey.data?.result_status === "superseded" ||
                      (journey.data?.scene_revision_id != null &&
                        journey.data.scene_revision_id !==
                          sceneBoundariesQuery.data?.confirmed_revision?.revision_id)) ? (
                      <div className="shell-banner" data-testid="reader-journey-historical-banner">
                        <strong>历史阅读旅程</strong>
                        <span>
                          该结果基于场景修订 #{journey.data?.scene_revision_id ?? "-"}。当前场景划分已经更新。
                        </span>
                        <button type="button" className="secondary" onClick={openSceneBoundaryReview}>
                          按当前场景重新生成
                        </button>
                      </div>
                    ) : null}
                    {!journeyExplicitMissing ? (
                      <WorkspaceJourneyPane
                        bookId={bookId}
                        chapterId={chapterId!}
                        chapterTitle={chapterTitle}
                        analysisRunId={analysisRunId}
                        journey={journey.data}
                        mainContentState={workspaceLayout.mainContentState}
                        onRetry={() => void journey.refetch()}
                        onReading={() => setView("reading", "user")}
                        onViewScene={() => setResultTab("analysis", "user")}
                      />
                    ) : null}
                  </>
                ) : null}
              </>
            ) : null}
          </div>

          {showProgressPanel ? (
            <aside data-testid="context-pane" className="book-shell-context">
              <ChapterAnalysisProgressPanel
                run={progress.run}
                uiState={
                  progress.isLoading && !progress.run
                    ? "creating"
                    : activeTab === "journey" && resolvedCurrentJourney.journey
                      ? journeySidebarUi.sidebarUiState === "idle"
                        ? compositionUiState !== "idle"
                          ? compositionUiState
                          : progress.uiState
                        : journeySidebarUi.sidebarUiState
                      : compositionUiState !== "idle"
                        ? compositionUiState
                        : progress.uiState === "idle" && analysisRunId
                          ? "running"
                          : progress.uiState
                }
                chapterTitle={chapterTitle}
                reconnectHint={progress.reconnectHint}
                canResume={progress.canResume}
                elapsedOverride={
                  activeTab === "journey"
                    ? formatJourneyElapsed(selectedJourneyElapsedMs)
                    : undefined
                }
                progressOverride={
                  activeTab === "journey" && resolvedCurrentJourney.journey
                    ? {
                        current:
                          resolvedCurrentJourney.journey.completed_scene_count ??
                          journeyProgress.data?.completed_scene_count ??
                          0,
                        total:
                          resolvedCurrentJourney.journey.total_scene_count ??
                          journeyProgress.data?.total_scene_count ??
                          0,
                      }
                    : null
                }
                statusLabelOverride={
                  activeTab === "journey" && resolvedCurrentJourney.journey
                    ? journeySidebarUi.label
                    : undefined
                }
                onResume={progress.resume}
                onReanalyze={() => setDialog(true)}
              onReviewBoundary={() => {
                if (sceneBoundaryReviewActive) openSceneBoundaryReview();
                else setReviewOpen(true);
              }}
                onDismiss={() => setPanelCollapsed(true)}
                onContinueReading={() => setView("reading", "user")}
                onViewResults={() => {
                  setResultTab("analysis", "user");
                }}
                onContinueReaderJourney={() => {
                  if (
                    compositionUiState === "awaiting_reader_journey_start" &&
                    progress.run
                  ) {
                    void (async () => {
                      try {
                        await analysisRecoveryApi.recover(progress.run!.id, {
                          client_request_id: getOrCreateJourneyClientRequestId(progress.run!.id),
                          cloud_consent: true,
                          confirmed: true,
                          recovery_mode: "unified",
                          resume: true,
                        });
                      } finally {
                        void qc.invalidateQueries({
                          queryKey: ["reader-journey"],
                        });
                        void journey.refetch();
                        void progress.refresh();
                        setResultTab("journey", "user");
                      }
                    })();
                    return;
                  }
                  setResultTab("journey", "user");
                }}
                onBudgetContinued={() => void progress.refresh()}
                journeyPageActive={
                  showJourneyActive ||
                  journeyActiveView ||
                  chapterPresentation.is_journey_active
                }
                journeyStatus={
                  journeyProgress.data?.status ||
                  journey.data?.status ||
                  progress.run?.journey_status ||
                  null
                }
              />
            </aside>
          ) : null}
        </div>
      )}

      <ChapterNavigatorDrawer
        open={catalogOpen}
        bookTitle={bookTitle}
        chapters={chapters.data || []}
        currentChapterId={chapterId}
        onClose={() => setCatalogOpen(false)}
        onSelectChapter={selectChapterFromCatalog}
      />

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
          onCreated={(runId, meta) => {
            bindAnalysisRun(runId, meta);
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
