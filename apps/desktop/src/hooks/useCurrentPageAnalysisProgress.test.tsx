import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { analysisApi } from "../services/analysisApi";
import { useCurrentPageAnalysisProgress } from "./useCurrentPageAnalysisProgress";

vi.mock("../services/analysisApi", () => ({
  analysisApi: {
    run: vi.fn(),
    resumeSceneAnalysis: vi.fn(),
    recoverPreflight: vi.fn(),
    continueFromCheckpoints: vi.fn(),
  },
}));

function wrapper(client: QueryClient) {
  return function W({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function baseRun(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: 55,
    subject_id: "2",
    provider: "fake",
    model: "fake",
    status,
    progress_current: 1,
    progress_total: 4,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: false,
    created_at: "2026-01-01T00:00:00Z",
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    completed_scene_count: 2,
    total_scene_count: 14,
    ...extra,
  };
}

describe("useCurrentPageAnalysisProgress", () => {
  beforeEach(() => {
    vi.mocked(analysisApi.run).mockReset();
    vi.mocked(analysisApi.resumeSceneAnalysis).mockReset();
    vi.mocked(analysisApi.recoverPreflight).mockReset();
    vi.mocked(analysisApi.continueFromCheckpoints).mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("polls existing run detail and maps running state", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue(baseRun("scene_analysis_running") as any);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useCurrentPageAnalysisProgress({ runId: 55 }),
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(result.current.uiState).toBe("running"));
    expect(analysisApi.run).toHaveBeenCalledWith(55);
  });

  it("stops polling after succeeded", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue(baseRun("succeeded") as any);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useCurrentPageAnalysisProgress({ runId: 55 }),
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(result.current.uiState).toBe("succeeded"));
    const calls = vi.mocked(analysisApi.run).mock.calls.length;
    await new Promise((r) => setTimeout(r, 2500));
    expect(vi.mocked(analysisApi.run).mock.calls.length).toBe(calls);
  });

  it("maps UI state from last successful run snapshot (not from fetch errors)", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue(baseRun("scene_analysis_running") as any);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchInterval: false } },
    });
    const { result } = renderHook(
      () => useCurrentPageAnalysisProgress({ runId: 55 }),
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(result.current.uiState).toBe("running"));
    // Seed a successful snapshot, then force queryFn failures — placeholderData keeps the run.
    vi.mocked(analysisApi.run).mockRejectedValue(new Error("network"));
    client.setQueryData(["current-page-analysis-run", 55], baseRun("scene_analysis_running"));
    expect(result.current.uiState).toBe("running");
    expect(result.current.uiState).not.toBe("failed");
  });

  it("resume reuses the same run id via resumeSceneAnalysis", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue(
      baseRun("scene_analysis_partial", { scene_analysis_resume_available: true }) as any,
    );
    vi.mocked(analysisApi.resumeSceneAnalysis).mockResolvedValue({
      run_id: 55,
      status: "scene_analysis_running",
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useCurrentPageAnalysisProgress({ runId: 55 }),
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(result.current.canResume).toBe(true));
    await result.current.resume();
    expect(analysisApi.resumeSceneAnalysis).toHaveBeenCalledWith(
      55,
      expect.objectContaining({ confirmed: true, cloud_consent: true }),
    );
  });
});
