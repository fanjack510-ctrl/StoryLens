import { useMemo, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnalysisResultsPage } from "./AnalysisResultsPage";
import { CompactToolbar } from "../components/layout/CompactToolbar";
import { OverflowMenu } from "../components/layout/OverflowMenu";
import { ResultViewSwitcher } from "../components/layout/ResultViewSwitcher";
import { Empty, ErrorState, Loading } from "../components/common/States";
import { analysisApi } from "../services/analysisApi";
import { booksApi } from "../services/booksApi";
import { resolveRunResultsViewState } from "../services/runResultsGuard";
import { formatRunStatusForResults } from "./sceneResultLabels";
import "./analysisResults.css";

function clickResults(selector: string) {
  document.querySelector<HTMLElement>(selector)?.dispatchEvent(
    new MouseEvent("click", { bubbles: true, cancelable: true }),
  );
  const el = document.querySelector<HTMLButtonElement | HTMLAnchorElement>(selector);
  el?.click();
}

export function AnalysisResultsShellPage() {
  const params = useParams();
  const runId = Number(params.runId);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [techOpen, setTechOpen] = useState(false);

  const isJourney = searchParams.get("tab") === "reader-journey";
  const results = useQuery({
    queryKey: ["run-results", runId],
    queryFn: () => analysisApi.results(runId),
    enabled: Number.isFinite(runId),
  });

  const viewState = resolveRunResultsViewState({
    isLoading: results.isLoading,
    error: results.error,
    data: results.data,
  });

  const completedRun = viewState.kind === "completed" ? viewState.data.run : null;
  const completedChapter = viewState.kind === "completed" ? viewState.data.chapter : null;
  const failedChapter =
    viewState.kind === "failed" ? viewState.chapter : null;
  const chapter = completedChapter ?? failedChapter;
  const bookId = chapter != null ? chapter.book_id : undefined;
  const chapterId = chapter != null ? chapter.id : undefined;

  const journey = useQuery({
    queryKey: ["reader-journey", runId],
    queryFn: () => analysisApi.readerJourney(runId),
    enabled: Number.isFinite(runId) && completedRun != null && completedRun.status === "succeeded",
  });

  const bookQuery = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId!),
    enabled: bookId != null,
  });

  const journeyLabel = useMemo(() => {
    if (journey.data?.visualization) return "查看读者旅程";
    return "读者旅程";
  }, [journey.data?.visualization]);

  const setView = (view: "analysis" | "journey") => {
    const next = new URLSearchParams(searchParams);
    if (view === "journey") {
      next.set("tab", "reader-journey");
      // Prefer activating existing journey tab inside page
      setSearchParams(next, { replace: true });
      // Also click internal tab if analysis chrome is visible
      queueMicrotask(() => clickResults('[data-testid="tab-journey"]'));
    } else {
      next.delete("tab");
      next.delete("mode");
      next.delete("scene");
      next.delete("paragraph");
      next.delete("metric");
      next.delete("cluster");
      setSearchParams(next, { replace: true });
      queueMicrotask(() => clickResults('[data-testid="tab-structure"]'));
    }
  };

  const primaryActionsCount = 4; // 返回 / 分析视图 / 读者旅程 / 更多

  const shellChrome = (
    <>
      <CompactToolbar
        data-testid="results-shell-toolbar"
        title={
          <button
            type="button"
            className="ghost"
            data-testid="back-to-chapter"
            onClick={() => {
              if (bookId != null) navigate(`/books/${bookId}`);
              else navigate("/library");
            }}
          >
            返回章节
          </button>
        }
        secondary={
          <ResultViewSwitcher
            active={isJourney ? "journey" : "analysis"}
            onChange={setView}
            journeyLabel={journeyLabel}
          />
        }
        tertiary={
          <OverflowMenu
            data-testid="results-more-menu"
            items={[
              {
                id: "scene-structure",
                label: "章节结构",
                group: "查看",
                testId: "results-more-structure",
                onSelect: () => clickResults('[data-testid="open-scene-structure-drawer"]'),
              },
              {
                id: "history",
                label: "历史版本",
                group: "查看",
                testId: "results-more-history",
                onSelect: () => {
                  setView("analysis");
                  queueMicrotask(() => clickResults('[data-testid="tab-history"]'));
                },
              },
              {
                id: "tech",
                label: "技术信息",
                group: "查看",
                testId: "results-more-tech",
                onSelect: () => setTechOpen(true),
              },
              {
                id: "export-png",
                label: "导出旅程PNG",
                group: "导出",
                testId: "results-more-export-png",
                onSelect: () => {
                  clickResults('[data-testid="journey-export-png"]');
                },
              },
              {
                id: "export-json",
                label: "导出JSON",
                group: "导出",
                testId: "results-more-export-json",
                onSelect: () => clickResults('[data-testid="export-json"]'),
              },
              {
                id: "export-md",
                label: "导出Markdown",
                group: "导出",
                testId: "results-more-export-md",
                onSelect: () => clickResults('[data-testid="export-markdown"]'),
              },
              {
                id: "export-journey-json",
                label: "导出旅程JSON",
                group: "导出",
                testId: "results-more-export-journey-json",
                onSelect: () => clickResults('[data-testid="export-journey-json"]'),
              },
              {
                id: "tasks",
                label: "返回任务记录",
                group: "操作",
                testId: "results-more-tasks",
                onSelect: () => navigate(`/tasks?run_id=${runId}`),
              },
              {
                id: "reanalyze",
                label: "重新分析",
                group: "操作",
                testId: "results-more-reanalyze",
                onSelect: () => {
                  if (bookId != null) navigate(`/books/${bookId}`);
                },
              },
              {
                id: "boundary",
                label: "高级边界审阅",
                group: "操作",
                testId: "results-more-boundary",
                onSelect: () => {
                  if (bookId != null) navigate(`/books/${bookId}`);
                },
              },
            ]}
          />
        }
      />

      {techOpen && (
        <div className="shell-banner tech-info" data-testid="results-tech-info">
          <span>
            运行 #{runId}
            {journey.data?.journey_run_id
              ? ` · 旅程任务 #${journey.data.journey_run_id}`
              : ""}
            {completedRun?.provider ? ` · 服务商 ${completedRun.provider}` : ""}
            {completedRun?.prompt_version
              ? ` · 提示词 ${completedRun.prompt_version}`
              : ""}
            {bookQuery.data?.title ? ` · ${bookQuery.data.title}` : ""}
            {chapterId != null ? ` · 章节 ${chapterId}` : ""}
          </span>
          <button type="button" onClick={() => setTechOpen(false)}>
            关闭
          </button>
        </div>
      )}
    </>
  );

  let body: ReactNode;
  if (!Number.isFinite(runId)) {
    body = (
      <Empty text="无效的分析运行 ID" />
    );
  } else if (viewState.kind === "loading") {
    body = <Loading />;
  } else if (viewState.kind === "error") {
    body = (
      <ErrorState error={viewState.error} retry={() => void results.refetch()} />
    );
  } else if (viewState.kind === "missing") {
    body = (
      <div className="state results-page-state" data-testid="results-empty-missing">
        <strong>未找到分析结果</strong>
        <span>该运行可能尚不存在，或结果尚未生成。</span>
      </div>
    );
  } else if (viewState.kind === "incomplete") {
    body = (
      <div className="state results-page-state" data-testid="results-empty-incomplete">
        <strong>分析结果数据不完整</strong>
        <span>{viewState.reason}</span>
      </div>
    );
  } else if (viewState.kind === "failed") {
    body = (
      <div className="state results-page-state" data-testid="results-empty-failed">
        <strong>分析尚未完成</strong>
        <span>
          当前状态：{formatRunStatusForResults(viewState.status)}。请返回任务中心查看进度，或等待分析成功后再打开结果。
        </span>
      </div>
    );
  } else {
    body = <AnalysisResultsPage />;
  }

  return (
    <div
      className={`results-shell-simplified results-shell--compact ${isJourney ? "is-journey results-shell--journey" : "is-analysis results-shell--analysis"}`}
      data-testid="results-shell"
      data-shell-mode={isJourney ? "journey" : "analysis"}
      data-result-view={isJourney ? "journey" : "analysis"}
      data-primary-actions={primaryActionsCount}
      data-results-state={viewState.kind}
    >
      {shellChrome}
      <div className="results-shell-body">{body}</div>
    </div>
  );
}
