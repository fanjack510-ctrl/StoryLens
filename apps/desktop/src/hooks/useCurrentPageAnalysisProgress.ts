import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "../services/analysisApi";
import type { Run } from "../types";
import {
  isTerminalUiState,
  mapRunToUiState,
  type ChapterAnalysisUiState,
} from "../components/chapterAnalysis/mapAnalysisUiState";

const POLL_MS = 2000;
const HIDDEN_POLL_MS = 12000;

type Options = {
  runId: number | null;
  enabled?: boolean;
};

/**
 * Polls existing AnalysisRun detail API for current-page progress composition.
 * Does not create runs, does not call Reader Journey APIs.
 */
export function useCurrentPageAnalysisProgress({ runId, enabled = true }: Options) {
  const [visible, setVisible] = useState(
    () => typeof document === "undefined" || document.visibilityState === "visible",
  );
  const [reconnectHint, setReconnectHint] = useState(false);
  const failStreak = useRef(0);
  const refetchRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    const onVis = () => {
      const next = document.visibilityState === "visible";
      setVisible(next);
      if (next) refetchRef.current();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const query = useQuery({
    queryKey: ["current-page-analysis-run", runId],
    queryFn: async () => {
      try {
        const run = await analysisApi.run(runId!);
        failStreak.current = 0;
        setReconnectHint(false);
        return run;
      } catch (error) {
        failStreak.current += 1;
        if (failStreak.current >= 2) setReconnectHint(true);
        throw error;
      }
    },
    enabled: enabled && !!runId && Number.isFinite(runId),
    refetchInterval: (q) => {
      const run = q.state.data as Run | undefined;
      const ui = mapRunToUiState(run);
      if (isTerminalUiState(ui)) return false;
      return visible ? POLL_MS : HIDDEN_POLL_MS;
    },
    refetchOnWindowFocus: true,
    retry: 2,
    retryDelay: 1500,
    placeholderData: (prev) => prev,
  });

  refetchRef.current = () => {
    void query.refetch();
  };

  const run = query.data ?? null;
  const uiState: ChapterAnalysisUiState = useMemo(
    () => (runId ? mapRunToUiState(run) : "idle"),
    [run, runId],
  );

  const refresh = useCallback(async () => {
    if (!runId) return;
    try {
      await query.refetch();
    } catch {
      /* Transient network errors keep the last snapshot; UI shows reconnect hint. */
    }
  }, [query, runId]);

  const resume = useCallback(async () => {
    if (!run) return;
    if (run.scene_analysis_resume_available) {
      await analysisApi.resumeSceneAnalysis(run.id, {
        client_request_id: crypto.randomUUID(),
        cloud_consent: true,
        confirmed: true,
      });
    } else if (run.detection_recovery_available || run.checkpoint_available) {
      const pre = await analysisApi.recoverPreflight(run.id, { cloud_consent: true });
      await analysisApi.continueFromCheckpoints(run.id, {
        client_request_id: crypto.randomUUID(),
        cloud_consent: true,
        confirmed: true,
        provider_state_version: pre.provider_state_version,
      });
    } else {
      throw new Error("当前任务暂不支持恢复");
    }
    await refresh();
  }, [refresh, run]);

  return {
    run,
    uiState,
    isLoading: query.isLoading && !run,
    isFetching: query.isFetching,
    reconnectHint,
    refresh,
    resume,
    canResume: Boolean(
      run &&
        (run.scene_analysis_resume_available ||
          uiState === "awaiting_budget_adjustment" ||
          run.detection_recovery_available ||
          (run.checkpoint_available &&
            (uiState === "partial" || uiState === "failed"))),
    ),
  };
}
