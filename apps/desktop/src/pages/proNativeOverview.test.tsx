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
import {
  FIXTURE_ENGINE_ID,
  FIXTURE_ENGINE_LABEL,
  FORMAL_ENGINE_LABEL,
  PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
} from "../services/proNativeOverviewFlag";
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
const retrySpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "retryRun");
const resumeSpy = vi.spyOn(proNativeOverviewApiMod.proNativeOverviewApi, "resumeRun");

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
    engine_id: FIXTURE_ENGINE_ID,
    provider_id: "fixture",
    model_id: FIXTURE_ENGINE_ID,
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
    progress: {
      completed_windows: 1,
      total_windows: 2,
      current_window_index: 1,
    },
    estimated_tokens: 8000,
    actual_tokens: 1200,
    estimated_cost: 0.12,
    actual_cost: 0.02,
    currency: "CNY",
    provider: "fixture",
    model: FIXTURE_ENGINE_ID,
    engine_id: FIXTURE_ENGINE_ID,
    retryable: false,
    actions: { can_retry: false, can_resume: false },
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
        confidence: 0.4,
        evidence_refs: ["ev-1", "ev-2"],
        status: "conflicted",
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
    engine_id: FIXTURE_ENGINE_ID,
    engine_version: "walking-skeleton-1",
    prompt_version: "fixture-no-prompt",
    contract_version: "1.0",
    warnings: [],
  };
}

async function consentAndStart() {
  await screen.findByTestId("pro-native-overview-preflight");
  await fireEvent.click(screen.getByTestId("pro-native-overview-consent-checkbox"));
  await fireEvent.click(screen.getByTestId("pro-native-overview-start"));
}

describe("Pro Native Overview UI (STEP 2.3-C)", () => {
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
    retrySpy.mockReset();
    resumeSpy.mockReset();
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

  it("shows complete preflight + consent with Fixture engine labeling", async () => {
    stubEntitlements(true);
    preflightSpy.mockResolvedValue(basePreflight());
    renderApp("/books/1/pro-native-overview");
    const panel = await screen.findByTestId("pro-native-overview-preflight");
    expect(panel).toHaveTextContent("章节数：2");
    expect(panel).toHaveTextContent("段落数：4");
    expect(panel).toHaveTextContent("字符数：1200");
    expect(screen.getByTestId("pro-native-overview-preflight-windows")).toHaveTextContent(
      "预估窗口：2",
    );
    expect(screen.getByTestId("pro-native-overview-preflight-tokens")).toHaveTextContent("8000");
    expect(screen.getByTestId("pro-native-overview-preflight-cost")).toHaveTextContent("0.1200");
    expect(screen.getByTestId("pro-native-overview-preflight-provider")).toHaveTextContent(
      "fixture",
    );
    expect(screen.getByTestId("pro-native-overview-preflight-model")).toHaveTextContent(
      FIXTURE_ENGINE_ID,
    );
    expect(screen.getByTestId("pro-native-overview-preflight-engine")).toHaveTextContent(
      FIXTURE_ENGINE_LABEL,
    );
    expect(screen.getByTestId("pro-native-overview-engine-badge")).toHaveAttribute(
      "data-engine-kind",
      "fixture",
    );
    expect(screen.getByTestId("pro-native-overview-walking-notice")).toHaveTextContent(
      "当前为行走骨架验证，不调用真实 AI Provider。",
    );
    expect(screen.getByTestId("pro-native-overview-consent")).toBeInTheDocument();
    expect(screen.getByTestId("pro-native-overview-start")).toBeDisabled();
    expect(screen.getByTestId("pro-native-overview-product-distinction")).toHaveTextContent(
      "章节聚合洞察",
    );
  });

  it("labels formal engine distinctly from Fixture", async () => {
    stubEntitlements(true);
    preflightSpy.mockResolvedValue(
      basePreflight({
        engine_id: PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
        provider_id: "aliyun_qwen",
        model_id: "qwen-plus",
        provider_configured: true,
      }),
    );
    renderApp("/books/1/pro-native-overview");
    await screen.findByTestId("pro-native-overview-preflight");
    expect(screen.getByTestId("pro-native-overview-engine-badge")).toHaveAttribute(
      "data-engine-kind",
      "formal",
    );
    expect(screen.getByTestId("pro-native-overview-preflight-engine")).toHaveTextContent(
      FORMAL_ENGINE_LABEL,
    );
    expect(screen.getByTestId("pro-native-overview-formal-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("pro-native-overview-walking-notice")).not.toBeInTheDocument();
  });

  it("create run requires consent then moves to multi-stage progress", async () => {
    stubEntitlements(true);
    preflightSpy.mockResolvedValue(basePreflight());
    createSpy.mockResolvedValue({
      run_id: "101",
      book_id: "1",
      snapshot_id: "55",
      status: "pending",
      progress: { completed_windows: 0, total_windows: 2 },
    });
    getRunSpy.mockResolvedValue(analyzingRun());
    renderApp("/books/1/pro-native-overview");
    await consentAndStart();
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    await waitFor(() => expect(getRunSpy).toHaveBeenCalledWith("101"));
    expect(await screen.findByTestId("pro-native-overview-status")).toHaveTextContent(
      "analyzing",
    );
    expect(screen.getByTestId("pro-native-overview-window-progress")).toHaveTextContent(
      "1 / 2",
    );
    expect(screen.getByTestId("pro-native-overview-window-progress").textContent).not.toMatch(
      /%/,
    );
    expect(screen.getByTestId("pro-native-overview-tokens")).toHaveTextContent("8000");
    expect(screen.getByTestId("pro-native-overview-cost")).toHaveTextContent("0.1200");
    expect(
      screen.getByTestId("pro-native-overview-stage-item-extract_overview_facts"),
    ).toHaveAttribute("data-stage-state", "current");
    expect(
      screen.getByTestId("pro-native-overview-stage-item-snapshot_preflight"),
    ).toHaveAttribute("data-stage-state", "done");
  });

  it("shows completed result field statuses, evidence, and native coverage", async () => {
    stubEntitlements(true);
    getRunSpy.mockResolvedValue(analyzingRun({ status: "completed", current_stage: "finalize" }));
    getOverviewSpy.mockResolvedValue(completedOverview());
    renderApp("/books/1/pro-native-overview?run_id=101");
    const result = await screen.findByTestId("pro-native-overview-result");
    expect(result).toHaveTextContent("林远");
    expect(screen.getByTestId("pro-native-overview-field-protagonist-status")).toHaveTextContent(
      "已支持",
    );
    expect(
      screen.getByTestId("pro-native-overview-field-key_turning_points-status"),
    ).toHaveTextContent("低置信度");
    expect(
      screen.getByTestId("pro-native-overview-field-ending_state-insufficient"),
    ).toHaveTextContent("暂未能可靠判断");
    expect(screen.getByTestId("pro-native-overview-field-logline-status")).toHaveTextContent(
      "存在冲突",
    );
    expect(screen.getByTestId("pro-native-overview-field-logline-conflicted")).toBeInTheDocument();
    const coverage = screen.getByTestId("pro-native-overview-coverage");
    expect(coverage).toHaveTextContent("段落覆盖：4 / 4");
    expect(screen.getByTestId("pro-native-overview-coverage-note")).toHaveTextContent(
      "章节聚合洞察",
    );
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

  it("failed run exposes retry API action", async () => {
    stubEntitlements(true);
    getRunSpy.mockResolvedValue(
      analyzingRun({
        status: "failed",
        error: "窗口分析执行失败",
        error_code: "WINDOW_EXECUTION_FAILED",
        retryable: true,
        actions: { can_retry: true, can_resume: false },
        progress: {
          completed_windows: 1,
          total_windows: 2,
          failed_window_index: 1,
        },
      }),
    );
    retrySpy.mockResolvedValue({
      run_id: "101",
      book_id: "1",
      snapshot_id: "55",
      status: "analyzing",
      progress: { completed_windows: 1, total_windows: 2 },
      retryable: false,
      actions: { can_retry: false, can_resume: false },
    });
    renderApp("/books/1/pro-native-overview?run_id=101");
    expect(await screen.findByTestId("pro-native-overview-retryable")).toHaveTextContent("是");
    const err = await screen.findByTestId("pro-native-overview-error");
    expect(err).toHaveAttribute("data-error-code", "RUN_FAILED");
    await fireEvent.click(screen.getByTestId("pro-native-overview-retry-run"));
    await waitFor(() => expect(retrySpy).toHaveBeenCalledWith("101", expect.any(Object)));
  });

  it("paused run exposes resume API action", async () => {
    stubEntitlements(true);
    getRunSpy.mockResolvedValue(
      analyzingRun({
        status: "paused",
        actions: { can_retry: false, can_resume: true },
      }),
    );
    resumeSpy.mockResolvedValue({
      run_id: "101",
      book_id: "1",
      snapshot_id: "55",
      status: "analyzing",
      progress: { completed_windows: 1, total_windows: 2 },
      retryable: false,
      actions: { can_retry: false, can_resume: false },
    });
    renderApp("/books/1/pro-native-overview?run_id=101");
    expect(await screen.findByTestId("pro-native-overview-resumable")).toHaveTextContent("是");
    await fireEvent.click(screen.getByTestId("pro-native-overview-resume-run"));
    await waitFor(() => expect(resumeSpy).toHaveBeenCalledWith("101", expect.any(Object)));
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

  it("insights route smoke remains distinct from native overview", async () => {
    stubEntitlements(true);
    renderApp("/books/1/whole-book-insights");
    expect(await screen.findByText("insights-page")).toBeInTheDocument();
    expect(screen.queryByTestId("pro-native-overview-page")).not.toBeInTheDocument();
    expect(preflightSpy).not.toHaveBeenCalled();
  });

  it("preflight error surfaces recoverable error panel", async () => {
    stubEntitlements(true);
    const { ApiError } = await import("../services/apiClient");
    preflightSpy.mockRejectedValue(
      new ApiError("BOOK_CONTENT_EMPTY", "书籍没有可用于分析的正文段落。", 400),
    );
    renderApp("/books/1/pro-native-overview");
    await waitFor(() => {
      expect(screen.getByTestId("pro-native-overview-error")).toHaveAttribute(
        "data-error-code",
        "BOOK_EMPTY",
      );
    });
    expect(screen.getByTestId("pro-native-overview-retry")).toBeInTheDocument();
  });

  it("maps PROVIDER_TIMEOUT to dedicated recovery copy", async () => {
    stubEntitlements(true);
    const { ApiError } = await import("../services/apiClient");
    preflightSpy.mockRejectedValue(
      new ApiError("PROVIDER_TIMEOUT", "模型响应超时，请稍后重试。", 504),
    );
    renderApp("/books/1/pro-native-overview");
    await waitFor(() => {
      expect(screen.getByTestId("pro-native-overview-error")).toHaveAttribute(
        "data-error-code",
        "PROVIDER_TIMEOUT",
      );
    });
    expect(screen.getByText("模型响应超时")).toBeInTheDocument();
    expect(screen.getByTestId("pro-native-overview-retry")).toBeInTheDocument();
  });
});
