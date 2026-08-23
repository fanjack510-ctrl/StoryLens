/**
 * CHG-20260727-016 — single-chapter 1.1.0 release scope presentation.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BookRoutePage } from "./BookRoutePage";
import { ProNativeOverviewPage } from "./ProNativeOverviewPage";
import { WholeBookInsightsPage } from "./WholeBookInsightsPage";
import * as proNativeOverviewApiMod from "../services/proNativeOverviewApi";
import { isNativeOverviewRun } from "../services/runLifecycle";

const flagState = vi.hoisted(() => ({ enabled: false }));

vi.mock("../services/proNativeOverviewFlag", async () => {
  const actual = await vi.importActual<typeof import("../services/proNativeOverviewFlag")>(
    "../services/proNativeOverviewFlag",
  );
  return {
    ...actual,
    isProNativeOverviewUiEnabled: () => flagState.enabled,
  };
});

vi.mock("../services/productEdition", async () => {
  const actual = await vi.importActual<typeof import("../services/productEdition")>(
    "../services/productEdition",
  );
  return {
    ...actual,
    PRO_CAPABILITIES_SHIPPED: false,
  };
});

vi.mock("../components/onboarding/AiSetupBanner", () => ({
  AiSetupBanner: () => null,
}));

vi.mock("../components/onboarding/FirstLaunchWizard", () => ({
  FirstLaunchWizard: () => null,
}));

const createSpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "createRun");
const preflightSpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "preflight");

function renderBook(path = "/books/1?chapter=2&view=reading") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/books/:bookId" element={<BookRoutePage />} />
          <Route path="/books/:bookId/pro-native-overview" element={<ProNativeOverviewPage />} />
          <Route path="/books/:bookId/whole-book-insights" element={<WholeBookInsightsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("single-chapter release scope (CHG-20260727-016)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    flagState.enabled = false;
  });

  beforeEach(() => {
    flagState.enabled = false;
    createSpy.mockReset();
    preflightSpy.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const href = String(input);
        if (href.includes("/api/v1/entitlements")) {
          return new Response(
            JSON.stringify({
              edition: "free",
              edition_label: "免费版",
              pro_active: false,
              features: {},
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (href.includes("/api/v1/books/1/chapters")) {
          return new Response(
            JSON.stringify([
              {
                id: 2,
                book_id: 1,
                chapter_index: 1,
                title: "第一章",
                paragraph_count: 2,
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (href.match(/\/api\/v1\/books\/1(\?|$)/) || href.endsWith("/api/v1/books/1")) {
          return new Response(
            JSON.stringify({ id: 1, title: "测试书", chapter_count: 1 }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (href.includes("/api/v1/chapters/2/paragraphs")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (href.includes("/api/v1/analysis-runs")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  it("hides native overview, chapter aggregate, and independent journey entries", async () => {
    renderBook();
    await screen.findByTestId("book-shell-toolbar");
    expect(screen.queryByTestId("pro-native-overview-entry-free")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pro-native-overview-entry-pro")).not.toBeInTheDocument();
    expect(screen.queryByText("原生全书概览")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-insights-entry-free")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-insights-entry-pro")).not.toBeInTheDocument();
    expect(screen.queryByText(/章节聚合洞察/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("reader-journey-entry-analyze")).not.toBeInTheDocument();
    expect(screen.queryByText("分析读者旅程")).not.toBeInTheDocument();
    expect(screen.getByTestId("book-more-menu")).toBeInTheDocument();
  });

  it("native direct route shows coming soon without create", async () => {
    renderBook("/books/1/pro-native-overview");
    const page = await screen.findByTestId("pro-native-overview-coming-soon");
    expect(page).toHaveTextContent("该功能正在完善中，当前版本暂未开放");
    expect(screen.queryByTestId("pro-native-overview-start")).not.toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
    expect(preflightSpy).not.toHaveBeenCalled();
  });

  it("chapter aggregate direct route shows coming soon", async () => {
    renderBook("/books/1/whole-book-insights");
    const page = await screen.findByTestId("whole-book-insights-coming-soon");
    expect(page).toHaveTextContent("该功能正在完善中，当前版本暂未开放");
  });

  it("classifies native overview runs for task-center filtering", () => {
    expect(
      isNativeOverviewRun({
        id: 14,
        task_type: "whole_book_overview",
        subject_type: "book",
        status: "completed",
      } as any),
    ).toBe(true);
    expect(
      isNativeOverviewRun({
        id: 13,
        task_type: "scene_pipeline",
        subject_type: "chapter",
        status: "scene_analysis_running",
      } as any),
    ).toBe(false);
  });
});
