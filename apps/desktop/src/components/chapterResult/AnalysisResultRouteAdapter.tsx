import { useContext, useMemo } from "react";
import { UNSAFE_RouteContext as RouteContext } from "react-router-dom";
import { AnalysisResultsPage } from "../../pages/AnalysisResultsPage";

type Props = {
  runId: number;
};

/**
 * Embeds frozen AnalysisResultsPage under /books?... without copying it.
 *
 * AnalysisResultsPage only needs:
 * - useParams().runId
 * - useSearchParams() (reads/writes the current location search)
 *
 * Nested MemoryRouter is forbidden under BrowserRouter, so we inject a synthetic
 * RouteContext match that supplies :runId while keeping the parent /books URL
 * (and its journey selection query keys) as the single source of truth.
 */
export function AnalysisResultRouteAdapter({ runId }: Props) {
  const parent = useContext(RouteContext);

  const value = useMemo(() => {
    const parentMatches = parent.matches ?? [];
    const parentParams = parentMatches[parentMatches.length - 1]?.params ?? {};
    const syntheticMatch = {
      id: `embedded-analysis-results-${runId}`,
      pathname: `/analysis-runs/${runId}/results`,
      pathnameBase: `/analysis-runs/${runId}/results`,
      params: { ...parentParams, runId: String(runId) },
      data: undefined,
      handle: undefined,
      route: {
        id: `embedded-analysis-results-${runId}`,
        path: "analysis-runs/:runId/results",
      },
    };

    return {
      outlet: null,
      matches: [...parentMatches, syntheticMatch],
      isDataRoute: parent.isDataRoute ?? false,
    };
  }, [parent.isDataRoute, parent.matches, runId]);

  return (
    <div className="analysis-result-route-adapter" data-testid="analysis-result-route-adapter">
      <RouteContext.Provider value={value}>
        <AnalysisResultsPage />
      </RouteContext.Provider>
    </div>
  );
}
