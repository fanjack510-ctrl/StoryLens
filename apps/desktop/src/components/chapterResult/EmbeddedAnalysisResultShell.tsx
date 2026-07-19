import { Component, type ErrorInfo, type ReactNode, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { AnalysisResultRouteAdapter } from "./AnalysisResultRouteAdapter";
import { ChapterResultErrorState } from "./ChapterResultErrorState";
import { ChapterResultLoadingState } from "./ChapterResultLoadingState";
import "./chapterResult.css";

type Props = {
  runId: number;
  onReading: () => void;
};

class ResultErrorBoundary extends Component<
  { children: ReactNode; onReset: () => void; fallback: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[embedded-analysis-result]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

/**
 * Current-page composition shell around frozen AnalysisResultsPage.
 * Does not auto-create Reader Journey; only loads existing run results.
 */
export function EmbeddedAnalysisResultShell({ runId, onReading }: Props) {
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const [boundaryKey, setBoundaryKey] = useState(0);
  const isJourney = searchParams.get("tab") === "reader-journey";

  const results = useQuery({
    queryKey: ["run-results", runId],
    queryFn: () => analysisApi.results(runId),
    enabled: Number.isFinite(runId),
    retry: false,
  });

  const retry = () => {
    setBoundaryKey((k) => k + 1);
    void qc.invalidateQueries({ queryKey: ["run-results", runId] });
    void results.refetch();
  };

  if (results.isLoading) {
    return <ChapterResultLoadingState />;
  }

  if (results.isError || !results.data) {
    return (
      <ChapterResultErrorState
        onRetry={retry}
        onReading={onReading}
        independentHref={`/analysis-runs/${runId}/results`}
      />
    );
  }

  return (
    <div
      className={`embedded-analysis-result-shell results-shell-simplified ${isJourney ? "is-journey" : "is-analysis"}`}
      data-testid="embedded-analysis-result"
      data-run-id={runId}
      data-shell-mode={isJourney ? "journey" : "analysis"}
    >
      <ResultErrorBoundary
        key={boundaryKey}
        onReset={retry}
        fallback={
          <ChapterResultErrorState
            onRetry={retry}
            onReading={onReading}
            independentHref={`/analysis-runs/${runId}/results`}
          />
        }
      >
        <AnalysisResultRouteAdapter runId={runId} />
      </ResultErrorBoundary>
    </div>
  );
}
