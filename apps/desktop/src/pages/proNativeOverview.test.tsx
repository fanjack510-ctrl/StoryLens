import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BookRoutePage } from "./BookRoutePage";
import { ProNativeOverviewPage } from "./ProNativeOverviewPage";
import { LibraryPage } from "./LibraryPage";
import * as proNativeOverviewApiMod from "../services/proNativeOverviewApi";
import type {
  OverviewApiResponse,
  ProNativeOverviewPreflight,
  RunStatusResponse,
} from "../services/proNativeOverviewApi";
import { overviewEvidenceHref } from "../services/proNativeOverviewDeepLink";
import { useOnboardingStore } from "../stores/onboardingStore";

const flagState = vi.hoisted(() => ({ enabled: true }));

vi.mock("../services/proNativeOverviewFlag", async () => {
  const actual = await vi.importActual<typeof import("../services/proNativeOverviewFlag")>(
    "../services/proNativeOverviewFlag",
  );
  return {
    ...actual,
    isProNativeOverviewUiEnabled: () => flagState.enabled,
  };
});

vi.mock("../components/onboarding/QwenFirstLaunchBanner", () => ({
  QwenFirstLaunchBanner: () => null,
}));

vi.mock("../components/onboarding/FirstLaunchWizard", () => ({
  FirstLaunchWizard: () => null,
}));

const preflightSpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "preflight");
const createSpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "createRun");
const getRunSpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "getRun");
const getOverviewSpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "getOverview");

const booksList = vi.fn();

vi.mock("../services/booksApi", async () => {
  const actual = await vi.importActual<typeof import("../services/booksApi")>(
    "../services/booksApi",
  );
  return {
    ...actual,
    booksApi: {
      ...actual.booksApi,
      list: (...args: unknown[]) => booksList(...args),
      detail: vi.fn(async () => ({ id: 1, title: "测试书" })),
      chapters: vi.fn(async () => [
        {
          id: 2,
          book_id: 1,
          chapter_index: 1,
          title: "第1章",
          display_title: "第1章",
          section_type: "chapter",
        },
      ]),
    },
  };
});

function renderApp(initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/books/:bookId" element={<BookRoutePage />} />
          <Route path="/books/:bookId/pro-native-overview" element={<ProNativeOverviewPage />} />
          <Route path="/books/:bookId/whole-book-insights" element={<div>insights-page</div>} />
          <Route path="/settings" element={<div>settings-page</div>} />
          <Route path="/library" element={<LibraryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubEntitlements(isPro: boolean) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo) => {
      const href = String(input);
      if (href.includes("/api/v1/entitlements")) {
        return new Response(
          JSON.stringify({
            edition: isPro ? "pro" : "free",
            edition_label: isPro ? "专业版" : "免费版",
            pro_active: isPro,
            features: { pro_whole_book_insights: isPro },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.includes("/api/v1/books/1")) {
        if (href.includes("/chapters")) {
          return new Response(
            JSON.stringify([
              {
                id: 2,
                book_id: 1,
                chapter_index: 1,
                title: "第1章",
                display_title: "第1章",
                section_type: "chapter",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (!href.includes("whole-book")) {
          return new Response(JSON.stringify({ id: 1, title: "测试书" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
      }
      if (href.includes("/api/v1/analysis-runs")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (href.includes("/api/v1/chapters/")) {
        return new Response(
          JSON.stringify({ items: [], offset: 0, limit: 200, total: 0, has_more: false }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ error_code: "HTTP_ERROR" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function basePreflight(
  overrides: Partial<ProNativeOverviewPreflight> = {},
): ProNativeOverviewPreflight {
  return {
    book_id: "1",
    chapter_count: 2,
    paragraph_count: 4,
    character_count: 1200,
    license_allowed: true,
    provider_configured: true,
    mode: "whole_book_native",
    estimated_windows: 2,
    estimated_tokens: 8000,
    estimated_cost: 0.12,
    currency: "CNY",
    warnings: [],
    blocking_errors: [],
    run_creation_enabled: true,
    ...overrides,
  };
}

function analyzingRun(overrides: Partial<RunStatusResponse> = {}): RunStatusResponse {
  return {
    run_id: "101",
    book_id: "1",
    snapshot_id: "55",
    status: "analyzing",
    current_stage: "extract_overview_facts",
    progress: { completed_windows: 1, total_windows: 2, percent: 50 },
    retryable: false,
    error: null,
    error_code: null,
    ...overrides,
  };
}

function completedOverview(): OverviewApiResponse {
  return {
    run: { run_id: "101", status: "completed" },
    book: { book_id: "1", title: "测试书" },
    snapshot: { snapshot_id: "55", status: "completed" },
    coverage: {
      original_paragraphs_total: 4,
      original_paragraphs_covered: 4,
      original_coverage_percent: 100,
      windows_total: 2,
      windows_completed: 2,
      evidence_count: 1,
    },
    overview: {
      protagonist: {
        value: "林远",
        confidence: 0.9,
        evidence_refs: ["ev-1"],
        status: "supported",
      },
      protagonist_core_goal: {
        value: "寻找真相",
        confidence: 0.8,
        evidence_refs: ["ev-1"],
        status: "supported",
      },
      primary_conflict: {
        value: "真相与谎言",
        confidence: 0.7,
        evidence_refs: ["ev-1"],
        status: "supported",
      },
      central_question: {
        value: "钟声从何处来？",
        confidence: 0.6,
        evidence_refs: ["ev-1"],
        status: "supported",
      },
      key_turning_points: {
        value: ["听见钟声"],
        confidence: 0.5,
        evidence_refs: ["ev-1"],
        status: "low_confidence",
      },
      ending_state: {
        value: null,
        confidence: 0,
        evidence_refs: [],
        status: "insufficient_evidence",
      },
      logline: {
        value: "雨巷中，林远循着钟声寻找真相。",
        confidence: 0.6,
        evidence_refs: ["ev-1"],
        status: "supported",
      },
      synopsis: {
        value: "短篇概要",
        confidence: 0.55,
        evidence_refs: ["ev-1"],
        status: "supported",
      },
    },
    evidence_index: [
      {
        evidence_id: "ev-1",
        chapter_id: "2",
        paragraph_id: "p2",
        quote: "他听见远处钟声。",
        deep_link: {
          book_id: "1",
          chapter_id: "2",
          paragraph_id: "p2",
          content_hash: "abc123",
        },
      },
    ],
    generated_at: "2026-07-25T12:30:00Z",
    engine_version: "walking-skeleton-1",
    prompt_version: "fixture-no-prompt",
    contract_version: "1.0",
    warnings: [],
  };
}

describe("Pro Native Overview UI (§11.9)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    flagState.enabled = true;
  });

  beforeEach(() => {
    flagState.enabled = true;
    preflightSpy.mockReset();
    createSpy.mockReset();
    getRunSpy.mockReset();
    getOverviewSpy.mockReset();
    booksList.mockReset();
    stubEntitlements(false);
    useOnboardingStore.setState({ status: "completed" });
  });

  it("distinguishes entry naming from 章节聚合洞察", async () => {
    stubEntitlements(true);
    renderApp("/books/1?chapter=2&view=reading");
    const insights = await screen.findByTestId("whole-book-insights-entry-pro");
    const overview = await screen.findByTestId("pro-native-overview-entry-pro");
    expect(insights).toHaveTextContent("章节聚合洞察");
    expect(insights).not.toHaveTextContent("Pro 原生全书概览");
    expect(overview).toHaveTextContent("Pro 原生全书概览");
    expect(overview).not.toHaveTextContent("章节聚合洞察");
  });

  it("free entry shows Pro license prompt without create API", async () => {
    renderApp("/books/1?chapter=2&view=reading");
    const entry = await screen.findByTestId("pro-native-overview-entry-free");
    expect(entry).toHaveTextContent("Pro 原生全书概览");
    await fireEvent.click(entry);
    const prompt = await screen.findByTestId("pro-native-overview-upgrade-prompt");
    expect(prompt).toHaveTextContent("Pro 原生全书概览");
    expect(prompt).toHaveTextContent("章节聚合洞察");
    expect(createSpy).not.toHaveBeenCalled();
    expect(preflightSpy).not.toHaveBeenCalled();
  });

  it("shows preflight counts, mode, engine, license, and walking notice", async () => {
    stubEntitlements(true);
    preflightSpy.mockResolvedValue(basePreflight());
    renderApp("/books/1/pro-native-overview");
    const panel = await screen.findByTestId("pro-native-overview-preflight");
    expect(panel).toHaveTextContent("章节数：2");
    expect(panel).toHaveTextContent("段落数：4");
    expect(panel).toHaveTextContent("字符数：1200");
    expect(panel).toHaveTextContent("模式：原生整书");
    expect(panel).toHaveTextContent("Engine：Fixture Development Mode");
    expect(panel).toHaveTextContent("已允许（Pro）");
    expect(screen.getByTestId("pro-native-overview-walking-notice")).toHaveTextContent(
      "当前为行走骨架验证，不调用真实 AI Provider。",
    );
    expect(screen.getByTestId("pro-native-overview-product-distinction")).toHaveTextContent(
      "章节聚合洞察",
    );
  });

  it("create run moves to running progress", async () => {
    stubEntitlements(true);
    preflightSpy.mockResolvedValue(basePreflight());
    createSpy.mockResolvedValue({
      run_id: "101",
      book_id: "1",
      snapshot_id: "55",
      status: "pending",
      progress: { completed_windows: 0, total_windows: 2, percent: 0 },
    });
    getRunSpy.mockResolvedValue(analyzingRun());
    renderApp("/books/1/pro-native-overview");
    await screen.findByTestId("pro-native-overview-preflight");
    await fireEvent.click(screen.getByTestId("pro-native-overview-start"));
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    await waitFor(() => expect(getRunSpy).toHaveBeenCalledWith("101"));
    expect(await screen.findByTestId("pro-native-overview-status")).toHaveTextContent(
      "analyzing",
    );
    expect(screen.getByTestId("pro-native-overview-window-progress")).toHaveTextContent(
      "1 / 2",
    );
  });

  it("shows completed result fields with confidence and evidence", async () => {
    stubEntitlements(true);
    getRunSpy.mockResolvedValue(analyzingRun({ status: "completed", current_stage: "finalize" }));
    getOverviewSpy.mockResolvedValue(completedOverview());
    renderApp("/books/1/pro-native-overview?run_id=101");
    const result = await screen.findByTestId("pro-native-overview-result");
    expect(result).toHaveTextContent("林远");
    expect(screen.getByTestId("pro-native-overview-field-protagonist")).toHaveTextContent(
      "置信度：0.90",
    );
    expect(
      screen.getByTestId("pro-native-overview-field-ending_state-insufficient"),
    ).toHaveTextContent("暂未能可靠判断");
    const evidence = screen.getByTestId("pro-native-overview-evidence-protagonist");
    expect(evidence).toHaveAttribute(
      "href",
      overviewEvidenceHref(1, {
        chapter_id: "2",
        paragraph_id: "p2",
        content_hash: "abc123",
      }),
    );
  });

  it("shows failed run state with retryable flag", async () => {
    stubEntitlements(true);
    getRunSpy.mockResolvedValue(
      analyzingRun({
        status: "failed",
        error: "窗口分析执行失败",
        error_code: "WINDOW_EXECUTION_FAILED",
        retryable: true,
      }),
    );
    renderApp("/books/1/pro-native-overview?run_id=101");
    await waitFor(() => expect(getRunSpy).toHaveBeenCalledWith("101"));
    expect(await screen.findByTestId("pro-native-overview-retryable")).toHaveTextContent(
      "是",
    );
    const err = await screen.findByTestId("pro-native-overview-error");
    expect(err).toHaveAttribute("data-error-code", "RUN_FAILED");
  });

  it("evidence deep link uses existing reader query shape", () => {
    expect(
      overviewEvidenceHref(9, { chapter_id: "3", paragraph_id: "p-9", content_hash: "h1" }),
    ).toBe("/books/9?chapter=3&paragraph=p-9&view=reading&paragraphContentHash=h1");
  });

  it("refresh reload uses run_id query to re-fetch from API", async () => {
    stubEntitlements(true);
    getRunSpy.mockResolvedValue(analyzingRun({ status: "completed" }));
    getOverviewSpy.mockResolvedValue(completedOverview());
    renderApp("/books/1/pro-native-overview?run_id=101");
    await screen.findByTestId("pro-native-overview-result");
    expect(getRunSpy).toHaveBeenCalledWith("101");
    expect(getOverviewSpy).toHaveBeenCalledWith("101");
    await fireEvent.click(screen.getByTestId("pro-native-overview-refresh"));
    await waitFor(() => expect(getRunSpy.mock.calls.length).toBeGreaterThan(1));
  });

  it("hides formal entry when feature flag is off", async () => {
    flagState.enabled = false;
    stubEntitlements(true);
    renderApp("/books/1?chapter=2&view=reading");
    await screen.findByTestId("whole-book-insights-entry-pro");
    expect(screen.queryByTestId("pro-native-overview-entry-pro")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pro-native-overview-entry-free")).not.toBeInTheDocument();
  });

  it("flag-off direct URL shows feature disabled, not white screen", async () => {
    flagState.enabled = false;
    stubEntitlements(true);
    renderApp("/books/1/pro-native-overview");
    const page = await screen.findByTestId("pro-native-overview-feature-disabled");
    expect(page).toHaveTextContent("功能未启用");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Pro 原生全书概览");
  });

  it("book workspace still renders with overview entry (no white screen)", async () => {
    stubEntitlements(true);
    renderApp("/books/1?chapter=2&view=reading");
    expect(await screen.findByTestId("pro-native-overview-entry-pro")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-insights-entry-pro")).toBeInTheDocument();
    expect(document.body.textContent?.trim().length).toBeGreaterThan(0);
  });

  it("Free library smoke remains unaffected", async () => {
    booksList.mockResolvedValue([
      {
        id: 1,
        title: "虚构星港编年史",
        source_file_name: "fiction_starport.txt",
        source_file_hash: "abc",
        created_at: "2026-07-01T00:00:00Z",
        revision_number: 1,
      },
    ]);
    renderApp("/library");
    expect(await screen.findByTestId("book-row-1")).toBeInTheDocument();
    expect(screen.getByTestId("library-search")).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });
});
