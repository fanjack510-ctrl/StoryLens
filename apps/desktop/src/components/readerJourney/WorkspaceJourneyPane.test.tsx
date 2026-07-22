import type { ReactElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { WorkspaceJourneyPane } from "./WorkspaceJourneyPane";
import {
  mapUrlToActiveTab,
  resolveWorkspaceLayout,
} from "../../services/resolveWorkspaceLayout";

vi.mock("./ReaderJourneySyncWorkspace", () => ({
  ReaderJourneySyncWorkspace: ({ variant }: { variant?: string }) => (
    <div data-testid="journey-sync-workspace" data-variant={variant}>
      <div data-testid="journey-sync-mode-toggle">
        <button type="button" data-testid="journey-mode-sync">
          正文对照
        </button>
        <button type="button" data-testid="journey-mode-journey">
          旅程视图
        </button>
        <button type="button" data-testid="journey-mode-reading">
          仅看正文
        </button>
      </div>
    </div>
  ),
}));

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    results: vi.fn(async () => ({ scenes: [] })),
  },
}));

afterEach(cleanup);

function renderPane(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("resolveWorkspaceLayout", () => {
  it("maps reader-journey URL to journey tab inside one workspace", () => {
    expect(
      mapUrlToActiveTab({
        requestedView: "result",
        requestedTab: "reader-journey",
        chapterComplete: true,
        journeyAvailable: true,
        sceneAvailable: true,
        userPinnedTab: null,
      }),
    ).toBe("journey");
  });

  it("keeps scene pin while journey completes", () => {
    const layout = resolveWorkspaceLayout({
      requestedView: "result",
      requestedTab: "reader-journey",
      userPinnedTab: "scene",
      chapterComplete: true,
      inFlight: false,
      sceneAvailable: true,
      journeyAvailable: true,
      journeyStatus: "succeeded",
      journeyQueryStatus: "success",
      journeyTrusted: true,
    });
    expect(layout.activeTab).toBe("scene");
    expect(layout.showProgressContext).toBe(false);
  });

  it("shows progress context only while in flight", () => {
    const layout = resolveWorkspaceLayout({
      requestedView: "result",
      requestedTab: null,
      userPinnedTab: "scene",
      chapterComplete: false,
      inFlight: true,
      sceneAvailable: true,
      journeyAvailable: false,
      journeyStatus: null,
      journeyQueryStatus: "idle",
    });
    expect(layout.activeTab).toBe("scene");
    expect(layout.showProgressContext).toBe(true);
    expect(layout.shellView).toBe("result");
  });

  it("keeps shellView=reading when user pins text while in flight", () => {
    const layout = resolveWorkspaceLayout({
      requestedView: "reading",
      requestedTab: null,
      userPinnedTab: "text",
      chapterComplete: false,
      inFlight: true,
      sceneAvailable: true,
      journeyAvailable: false,
      journeyStatus: null,
      journeyQueryStatus: "idle",
    });
    expect(layout.activeTab).toBe("text");
    expect(layout.shellView).toBe("reading");
    expect(layout.showProgressContext).toBe(true);
  });

  it("distinguishes loading from error", () => {
    expect(
      resolveWorkspaceLayout({
        requestedView: "result",
        requestedTab: "reader-journey",
        userPinnedTab: null,
        chapterComplete: true,
        inFlight: false,
        sceneAvailable: true,
        journeyAvailable: false,
        journeyStatus: null,
        journeyQueryStatus: "loading",
      }).mainContentState,
    ).toBe("loading");
    expect(
      resolveWorkspaceLayout({
        requestedView: "result",
        requestedTab: "reader-journey",
        userPinnedTab: null,
        chapterComplete: true,
        inFlight: false,
        sceneAvailable: true,
        journeyAvailable: false,
        journeyStatus: null,
        journeyQueryStatus: "error",
      }).mainContentState,
    ).toBe("request_error");
  });

  it("keeps legacy_unverified journey ready instead of hard-blocking", () => {
    const layout = resolveWorkspaceLayout({
      requestedView: "result",
      requestedTab: "reader-journey",
      userPinnedTab: null,
      chapterComplete: true,
      inFlight: false,
      sceneAvailable: true,
      journeyAvailable: true,
      journeyStatus: "succeeded",
      journeyQueryStatus: "success",
      journeyIntegrityStatus: "legacy_unverified",
      journeyTrusted: false,
    });
    expect(layout.mainContentState).toBe("ready");
  });

  it("hard-blocks only data_integrity_failed", () => {
    expect(
      resolveWorkspaceLayout({
        requestedView: "result",
        requestedTab: "reader-journey",
        userPinnedTab: null,
        chapterComplete: true,
        inFlight: false,
        sceneAvailable: true,
        journeyAvailable: true,
        journeyStatus: "succeeded",
        journeyQueryStatus: "success",
        journeyIntegrityStatus: "data_integrity_failed",
        journeyTrusted: false,
      }).mainContentState,
    ).toBe("invalid_artifact");
  });
});

describe("WorkspaceJourneyPane", () => {
  it("does not show temporary-load error while loading", () => {
    renderPane(
      <WorkspaceJourneyPane
        bookId={9}
        chapterId={1220}
        analysisRunId={8}
        journey={undefined}
        mainContentState="loading"
        onRetry={() => undefined}
        onReading={() => undefined}
      />,
    );
    expect(screen.getByTestId("workspace-journey-pane")).toHaveAttribute("data-state", "loading");
    expect(screen.queryByText("分析结果暂时无法加载")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chapter-result-open-independent")).not.toBeInTheDocument();
  });

  it("shows legacy banner and restores internal mode switcher", () => {
    renderPane(
      <WorkspaceJourneyPane
        bookId={11}
        chapterId={1224}
        analysisRunId={11}
        journey={
          {
            status: "succeeded",
            journey_run_id: 10,
            integrity_status: "legacy_unverified",
            trusted: false,
            integrity: { status: "legacy_unverified", legacy_warning: "旧版分析尚未完成来源校验，仅供参考。" },
            visualization: {
              scene_nodes: [
                {
                  scene_ordinal: 1,
                  scores: { reading_momentum: 1, plot_progress: 1 },
                  engagement: { engagement_score: 1 },
                },
              ],
              phases: [{ ordinal: 1 }],
              curve_series: { curiosity: [{ scene_ordinal: 1, value: 1 }] },
            },
          } as any
        }
        mainContentState="ready"
        onRetry={() => undefined}
        onReading={() => undefined}
      />,
    );
    expect(screen.getByTestId("workspace-journey-legacy-banner")).toBeInTheDocument();
    expect(screen.getByTestId("journey-sync-workspace")).toHaveAttribute("data-variant", "workspace");
    expect(screen.getByTestId("journey-mode-sync")).toHaveTextContent("正文对照");
    expect(screen.getByTestId("journey-mode-reading")).toHaveTextContent("仅看正文");
    expect(screen.queryByTestId("workspace-journey-integrity-banner")).not.toBeInTheDocument();
  });

  it("shows invalid artifact without independent page CTA", () => {
    renderPane(
      <WorkspaceJourneyPane
        bookId={9}
        chapterId={1220}
        analysisRunId={8}
        journey={
          {
            status: "succeeded",
            journey_run_id: 7,
            integrity_status: "data_integrity_failed",
            trusted: false,
            visualization: {
              scene_nodes: [{ scene_ordinal: 1, integrity_blocked: true }],
              phases: [{ ordinal: 1 }],
              curve_series: { curiosity: [{ scene_ordinal: 1, value: 1 }] },
            },
          } as any
        }
        mainContentState="invalid_artifact"
        onRetry={() => undefined}
        onReading={() => undefined}
      />,
    );
    expect(screen.getByTestId("workspace-journey-integrity-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-sync-workspace")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chapter-result-open-independent")).not.toBeInTheDocument();
  });
});
