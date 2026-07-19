import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnalysisResultsPage } from "./AnalysisResultsPage";
import { CompactToolbar } from "../components/layout/CompactToolbar";
import { OverflowMenu } from "../components/layout/OverflowMenu";
import { ResultViewSwitcher } from "../components/layout/ResultViewSwitcher";
import { analysisApi } from "../services/analysisApi";
import { booksApi } from "../services/booksApi";

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
  const journey = useQuery({
    queryKey: ["reader-journey", runId],
    queryFn: () => analysisApi.readerJourney(runId),
    enabled: Number.isFinite(runId) && results.data?.run.status === "succeeded",
  });

  const chapterId = results.data?.chapter.id;
  const bookId = results.data?.chapter.book_id;
  const bookQuery = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId!),
    enabled: !!bookId,
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

  return (
    <div
      className={`results-shell-simplified results-shell--compact ${isJourney ? "is-journey results-shell--journey" : "is-analysis results-shell--analysis"}`}
      data-testid="results-shell"
      data-shell-mode={isJourney ? "journey" : "analysis"}
      data-result-view={isJourney ? "journey" : "analysis"}
      data-primary-actions={primaryActionsCount}
    >
      <CompactToolbar
        data-testid="results-shell-toolbar"
        title={
          <button
            type="button"
            className="ghost"
            data-testid="back-to-chapter"
            onClick={() => {
              if (bookId) navigate(`/books/${bookId}`);
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
                onSelect: () => clickResults('[data-testid="journey-export-png"]'),
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
                  if (bookId) navigate(`/books/${bookId}`);
                },
              },
              {
                id: "boundary",
                label: "高级边界审阅",
                group: "操作",
                testId: "results-more-boundary",
                onSelect: () => {
                  if (bookId) navigate(`/books/${bookId}`);
                },
              },
            ]}
          />
        }
      />

      {techOpen && (
        <div className="shell-banner tech-info" data-testid="results-tech-info">
          <span>
            Run #{runId}
            {journey.data?.journey_run_id
              ? ` · JourneyRun #${journey.data.journey_run_id}`
              : ""}
            {results.data?.run.provider ? ` · ${results.data.run.provider}` : ""}
            {results.data?.run.prompt_version
              ? ` · prompt ${results.data.run.prompt_version}`
              : ""}
            {bookQuery.data?.title ? ` · ${bookQuery.data.title}` : ""}
            {chapterId ? ` · Chapter ${chapterId}` : ""}
          </span>
          <button type="button" onClick={() => setTechOpen(false)}>
            关闭
          </button>
        </div>
      )}

      <div className="results-shell-body">
        <AnalysisResultsPage />
      </div>
    </div>
  );
}
