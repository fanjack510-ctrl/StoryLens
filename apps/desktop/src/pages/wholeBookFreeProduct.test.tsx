import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../components/layout/AppShell";
import { BookRoutePage } from "./BookRoutePage";
import { WholeBookFreeProductPage } from "./WholeBookFreeProductPage";
import * as freeApiMod from "../services/wholeBookFreeProductApi";
import { wholeBookEvidenceReaderHref, openEvidenceInReader } from "../services/wholeBookFreeEvidenceDeepLink";
import type {
  BookOverviewResultRow,
  EvidenceSourceDetail,
  NarrativeAssetRow,
  NarrativeEntityRow,
  NarrativeEvidenceRow,
  WholeBookRunRecord,
} from "../services/wholeBookFreeProductApi";

const productFlagState = vi.hoisted(() => ({ enabled: true }));
const fixtureFlagState = vi.hoisted(() => ({ enabled: false }));
const realProviderState = vi.hoisted(() => ({ enabled: false }));

vi.mock("../services/wholeBookFreeProductFlag", async () => {
  const actual = await vi.importActual<typeof import("../services/wholeBookFreeProductFlag")>(
    "../services/wholeBookFreeProductFlag",
  );
  return {
    ...actual,
    isWholeBookFreeProductEnabled: () => productFlagState.enabled,
  };
});

vi.mock("../services/wholeBookFixturePreviewFlag", async () => {
  const actual = await vi.importActual<typeof import("../services/wholeBookFixturePreviewFlag")>(
    "../services/wholeBookFixturePreviewFlag",
  );
  return {
    ...actual,
    isWholeBookFixturePreviewEnabled: () => fixtureFlagState.enabled,
  };
});

vi.mock("../services/wholeBookRealProviderFlag", async () => {
  const actual = await vi.importActual<typeof import("../services/wholeBookRealProviderFlag")>(
    "../services/wholeBookRealProviderFlag",
  );
  return {
    ...actual,
    isWholeBookRealProviderEnabled: () => realProviderState.enabled,
  };
});

vi.mock("../components/onboarding/QwenFirstLaunchBanner", () => ({
  QwenFirstLaunchBanner: () => null,
}));

vi.mock("../components/onboarding/FirstLaunchWizard", () => ({
  FirstLaunchWizard: () => null,
}));

const prepareSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "prepare");
const createRunSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "createRun");
const createFixtureSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "createFixtureRun");
const progressSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getProgress");
const capabilitiesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "productCapabilities");
const getOverviewSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getOverview");
const listEntitiesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listEntities");
const listAssetsSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listAssets");
const listEvidencesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listEvidences");
const getEvidenceSourceSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getEvidenceSource");
const listStagesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listStages");

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

function basePrepare(overrides: Partial<freeApiMod.WholeBookPrepareResponse> = {}) {
  return {
    book_id: 1,
    book_title: "测试书",
    chapter_count: 12,
    character_count: 120000,
    mode: "whole_book_native",
    mode_label: "原生全书分析",
    product_enabled: true,
    real_provider_enabled: false,
    run_creation_enabled: false,
    fixture_preview_enabled: false,
    latest_run: null,
    recoverable_run: null,
    snapshot_rebuild_required: false,
    estimate: {
      estimate_id: 9,
      book_id: 1,
      mode: "whole_book_native",
      estimated_windows: 20,
      estimated_provider_calls: 21,
      estimated_input_tokens: 100000,
      estimated_output_tokens: 20000,
      estimated_cost_min_cny: "1.20",
      estimated_cost_max_cny: "1.80",
      provider_name: "测试 Provider",
      model_name: "test-model",
      price_known: true,
      currency: "CNY",
    },
    recommended_limits: {
      max_provider_calls: 200,
      max_input_tokens: 500000,
      max_output_tokens: 100000,
      max_cost_budget_cny: "10.00",
    },
    blocking_reasons: [],
    warnings: [],
    ...overrides,
  } satisfies freeApiMod.WholeBookPrepareResponse;
}

function baseRun(status = "pending", overrides: Partial<WholeBookRunRecord> = {}): WholeBookRunRecord {
  return {
    run_id: 42,
    book_id: 1,
    snapshot_id: 11,
    mode: "whole_book_native",
    status,
    current_stage_code: status === "running" ? "extract_entities_events" : null,
    idempotency_key: "k1",
    engine_id: "fixture-engine",
    engine_version: "v1",
    contract_version: "whole_book_contract_v1",
    prompt_version: null,
    result_origin: status === "completed" ? "fixture" : "formal",
    input_usage: {
      full_text_snapshot_used: true,
      chapter_analysis_asset_count: 0,
      reader_journey_asset_count: 0,
      confirmed_whole_book_asset_count: 0,
    },
    consent_id: null,
    cost_policy_id: null,
    created_at: "2026-07-28T00:00:00Z",
    started_at: status !== "pending" ? "2026-07-28T00:01:00Z" : null,
    paused_at: null,
    completed_at: status === "completed" ? "2026-07-28T01:00:00Z" : null,
    failed_at: null,
    cancelled_at: null,
    failure_code: null,
    failure_message_safe: null,
    ...overrides,
  };
}

function baseOverview(): BookOverviewResultRow {
  return {
    result_version: "v1",
    contract_version: "whole_book_contract_v1",
    run_id: 42,
    book_id: 1,
    snapshot_id: 11,
    mode: "whole_book_native",
    result_origin: "fixture",
    status: "completed",
    important_entity_ids: [101],
    key_event_asset_ids: [201],
    warnings: [],
    created_at: "2026-07-28T01:00:00Z",
    claims: [
      {
        claim_key: "genre_and_narrative_features",
        availability: "available",
        summary: "玄幻升级流",
        confidence: 0.9,
        evidence_ids: [501],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "core_setting",
        availability: "available",
        summary: "修真世界",
        confidence: 0.85,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "protagonist",
        availability: "available",
        summary: "林凡",
        confidence: 0.88,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "protagonist_core_goal",
        availability: "insufficient_evidence",
        summary: "目标尚不明确",
        confidence: 0.4,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "main_conflict",
        availability: "available",
        summary: "正邪对立",
        confidence: 0.8,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "core_question",
        availability: "available",
        summary: "能否突破",
        confidence: 0.75,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "final_resolution",
        availability: "unavailable",
        summary: null,
        confidence: null,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "important_characters",
        availability: "available",
        summary: "师父、师妹",
        confidence: 0.7,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "key_events",
        availability: "available",
        summary: "入门试炼",
        confidence: 0.82,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
    ],
  };
}

function baseEvidenceSource(): EvidenceSourceDetail {
  return {
    evidence_id: 501,
    chapter_title: "第1章",
    chapter_index: 1,
    paragraph_index: 3,
    global_paragraph_index: 3,
    paragraph_text: "林凡踏入山门，心中忐忑。",
    quote_text: "踏入山门",
    start_offset: 2,
    end_offset: 6,
    quote_hash: "qh",
    paragraph_text_hash: "ph",
    state: "valid",
  };
}

function renderPage(initial = "/books/1/whole-book") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/books/:bookId" element={<BookRoutePage />} />
          <Route path="/books/:bookId/whole-book" element={<WholeBookFreeProductPage />} />
          <Route path="/library" element={<div>library</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderAppShell(initial = "/library") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/library" element={<div>library-page</div>} />
            <Route path="/books/:bookId" element={<BookRoutePage />} />
            <Route path="/books/:bookId/whole-book" element={<WholeBookFreeProductPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WholeBookFreeProduct (Wave D §18.2)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    productFlagState.enabled = true;
    fixtureFlagState.enabled = false;
    realProviderState.enabled = false;
  });

  beforeEach(() => {
    productFlagState.enabled = true;
    fixtureFlagState.enabled = false;
    realProviderState.enabled = false;
    prepareSpy.mockReset();
    createRunSpy.mockReset();
    createFixtureSpy.mockReset();
    progressSpy.mockReset();
    capabilitiesSpy.mockReset();
    getOverviewSpy.mockReset();
    listEntitiesSpy.mockReset();
    listAssetsSpy.mockReset();
    listEvidencesSpy.mockReset();
    getEvidenceSourceSpy.mockReset();
    listStagesSpy.mockReset();

    prepareSpy.mockResolvedValue(basePrepare());
    capabilitiesSpy.mockResolvedValue({
      capabilities: [
        {
          capability_id: "whole_book.overview",
          display_name: "全书总览",
          required_tier: "free",
          release_status: "available",
          access_status: "granted",
          reason_code: null,
        },
        {
          capability_id: "whole_book.structure",
          display_name: "故事结构",
          required_tier: "free",
          release_status: "planned",
          access_status: "planned",
          reason_code: "capability_planned",
        },
        {
          capability_id: "whole_book.storylines",
          display_name: "故事线",
          required_tier: "pro",
          release_status: "planned",
          access_status: "planned",
          reason_code: "capability_planned",
        },
      ],
    });

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
        if (href.includes("/api/v1/books/1") && !href.includes("whole-book")) {
          return new Response(JSON.stringify({ id: 1, title: "测试书" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (href.includes("/api/v1/books/1/chapters")) {
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
  });

  it("hides entry when feature flag is off", async () => {
    productFlagState.enabled = false;
    renderPage("/books/1");
    await screen.findByTestId("book-shell-toolbar");
    expect(screen.queryByTestId("whole-book-free-entry")).not.toBeInTheDocument();
  });

  it("shows entry on book detail page with title and description", async () => {
    renderPage("/books/1");
    const entry = await screen.findByTestId("whole-book-free-entry");
    expect(entry).toHaveTextContent("全书分析");
    expect(entry).toHaveTextContent(
      "从完整原文出发，分析全书总览、主要人物、关键事件、故事结构和章节功能。",
    );
    expect(entry).toHaveAttribute("href", "/books/1/whole-book");
    expect(entry).toHaveTextContent("开始全书分析");
  });

  it("does not expose whole-book in primary navigation", async () => {
    renderAppShell("/library");
    await screen.findByTestId("primary-nav");
    expect(screen.queryByTestId("nav-whole-book")).not.toBeInTheDocument();
    expect(screen.queryByText("/books/1/whole-book")).not.toBeInTheDocument();
  });

  it("renders prepare page with cost estimate and consent", async () => {
    renderPage("/books/1/whole-book");
    expect(await screen.findByTestId("whole-book-free-prepare")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-cost-estimate")).toHaveTextContent("预计窗口数");
    expect(screen.getByTestId("whole-book-free-cost-estimate")).toHaveTextContent("20");
    expect(screen.getByTestId("whole-book-free-consent-checkbox")).toBeInTheDocument();
    const start = screen.getByTestId("whole-book-free-start-formal");
    expect(start).toBeDisabled();
    expect(screen.getByTestId("whole-book-free-real-provider-disabled")).toHaveTextContent(
      "真实模型 Provider 尚未启用",
    );
  });

  it("requires consent before formal start when real provider is on", async () => {
    realProviderState.enabled = true;
    prepareSpy.mockResolvedValue(
      basePrepare({ real_provider_enabled: true, run_creation_enabled: true }),
    );
    renderPage("/books/1/whole-book");
    const start = await screen.findByTestId("whole-book-free-start-formal");
    expect(start).toBeDisabled();
    fireEvent.click(screen.getByTestId("whole-book-free-consent-checkbox"));
    await waitFor(() => expect(start).not.toBeDisabled());
  });

  it("shows fixture preview button separately from formal start", async () => {
    fixtureFlagState.enabled = true;
    renderPage("/books/1/whole-book");
    expect(await screen.findByTestId("whole-book-free-start-fixture")).toHaveTextContent(
      "使用测试数据预览页面",
    );
    expect(screen.getByTestId("whole-book-free-fixture-notice")).toHaveTextContent("测试数据");
    expect(screen.getByTestId("whole-book-free-start-fixture")).not.toHaveTextContent("开始分析");
    expect(screen.getByTestId("whole-book-free-start-formal")).toHaveTextContent("开始全书分析");
  });

  it("renders nine overview claims with insufficient_evidence handling", async () => {
    prepareSpy.mockResolvedValue(basePrepare({ latest_run: baseRun("completed") }));
    getOverviewSpy.mockResolvedValue({ overview: baseOverview() });
    listEvidencesSpy.mockResolvedValue({ evidences: [] });
    listEntitiesSpy.mockResolvedValue({ entities: [] });
    listAssetsSpy.mockResolvedValue({ assets: [], total: 0, offset: 0, limit: 50 });
    renderPage("/books/1/whole-book");
    await screen.findByTestId("whole-book-free-overview");
    expect(screen.getAllByTestId(/^whole-book-free-claim-(?!evidence)/).length).toBe(9);
    expect(screen.getByTestId("whole-book-free-claim-protagonist_core_goal")).toHaveAttribute(
      "data-availability",
      "insufficient_evidence",
    );
    expect(screen.getByTestId("whole-book-free-insufficient-evidence")).toHaveTextContent(
      "当前证据不足",
    );
  });

  it("lists characters from important_entity_ids only", async () => {
    prepareSpy.mockResolvedValue(basePrepare({ latest_run: baseRun("completed") }));
    getOverviewSpy.mockResolvedValue({ overview: baseOverview() });
    listEntitiesSpy.mockResolvedValue({
      entities: [
        {
          entity_id: 101,
          entity_type: "character",
          canonical_name: "林凡",
          aliases: [{ name: "小林", confidence: 0.8, evidence_ids: [] }],
          state: "candidate",
          confidence: 0.9,
          evidence_count: 2,
          event_count: 1,
          linked_evidences: [{ evidence_id: 501, state: "valid", confidence: 0.9 }],
        },
        {
          entity_id: 999,
          entity_type: "character",
          canonical_name: "路人甲",
          aliases: [],
          state: "candidate",
          confidence: 0.2,
          evidence_count: 0,
          event_count: 0,
        },
      ] satisfies NarrativeEntityRow[],
    });
    listAssetsSpy.mockResolvedValue({ assets: [], total: 0, offset: 0, limit: 50 });
    listEvidencesSpy.mockResolvedValue({ evidences: [] });
    renderPage("/books/1/whole-book");
    await screen.findByTestId("whole-book-free-overview");
    fireEvent.click(screen.getByTestId("whole-book-free-module-characters_events"));
    const list = await screen.findByTestId("whole-book-free-characters-list");
    expect(within(list).getByText("林凡")).toBeInTheDocument();
    expect(within(list).queryByText("路人甲")).not.toBeInTheDocument();
  });

  it("lists events from key_event_asset_ids", async () => {
    prepareSpy.mockResolvedValue(basePrepare({ latest_run: baseRun("completed") }));
    getOverviewSpy.mockResolvedValue({ overview: baseOverview() });
    listEntitiesSpy.mockResolvedValue({ entities: [] });
    listAssetsSpy.mockResolvedValue({
      assets: [
        {
          asset_id: 201,
          asset_type: "event",
          title: "入门试炼",
          summary: "主角参加试炼",
          state: "candidate",
          confidence: 0.85,
          evidence_count: 1,
          subject_entity_ids: [101],
          event_type: "trial",
          evidence_ids: [501],
        },
      ] satisfies NarrativeAssetRow[],
      total: 1,
      offset: 0,
      limit: 50,
    });
    listEvidencesSpy.mockResolvedValue({
      evidences: [
        {
          evidence_id: 501,
          state: "valid",
          confidence: 0.9,
          global_paragraph_index: 10,
        },
      ] satisfies NarrativeEvidenceRow[],
    });
    renderPage("/books/1/whole-book");
    await screen.findByTestId("whole-book-free-overview");
    fireEvent.click(screen.getByTestId("whole-book-free-module-characters_events"));
    fireEvent.click(screen.getByText("关键事件"));
    expect(await screen.findByTestId("whole-book-free-event-201")).toHaveTextContent("入门试炼");
  });

  it("shows planned modules without purchase UI", async () => {
    renderPage("/books/1/whole-book");
    await screen.findByTestId("whole-book-free-module-nav");
    expect(screen.getByTestId("whole-book-free-module-structure")).toHaveTextContent("开发中");
    expect(screen.getByTestId("whole-book-free-module-chapter_functions")).toHaveTextContent(
      "开发中",
    );
    expect(screen.getByTestId("whole-book-free-module-pro_depth")).toHaveTextContent(
      "后续版本开放",
    );
    expect(screen.queryByText("购买")).not.toBeInTheDocument();
    expect(screen.queryByText("价格")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("whole-book-free-module-pro_depth"));
    expect(await screen.findByTestId("whole-book-free-pro-planned")).toHaveTextContent(
      "后续版本开放",
    );
  });

  it("shows fixture banner when result_origin is fixture", async () => {
    prepareSpy.mockResolvedValue(
      basePrepare({ latest_run: baseRun("completed", { result_origin: "fixture" }) }),
    );
    getOverviewSpy.mockResolvedValue({ overview: baseOverview() });
    listEntitiesSpy.mockResolvedValue({ entities: [] });
    listAssetsSpy.mockResolvedValue({ assets: [], total: 0, offset: 0, limit: 50 });
    listEvidencesSpy.mockResolvedValue({ evidences: [] });
    renderPage("/books/1/whole-book");
    expect(await screen.findByTestId("whole-book-free-fixture-banner")).toHaveTextContent(
      "测试数据预览",
    );
  });

  it("builds evidence reader deeplink with offset params", () => {
    const source = baseEvidenceSource();
    const href = wholeBookEvidenceReaderHref(1, source, 1);
    expect(href).toContain("/books/1?");
    expect(href).toContain("view=reading");
    expect(href).toContain("evidenceId=501");
    expect(href).toContain("paragraphIndex=3");
    expect(href).toContain("startOffset=2");
    expect(href).toContain("endOffset=6");
  });

  it("opens evidence drawer and reader deeplink", async () => {
    prepareSpy.mockResolvedValue(basePrepare({ latest_run: baseRun("completed") }));
    getOverviewSpy.mockResolvedValue({ overview: baseOverview() });
    listEntitiesSpy.mockResolvedValue({ entities: [] });
    listAssetsSpy.mockResolvedValue({ assets: [], total: 0, offset: 0, limit: 50 });
    listEvidencesSpy.mockResolvedValue({ evidences: [] });
    getEvidenceSourceSpy.mockResolvedValue({ source: baseEvidenceSource() });
    renderPage("/books/1/whole-book");
    await screen.findByTestId("whole-book-free-claim-evidence-genre_and_narrative_features");
    fireEvent.click(
      screen.getByTestId("whole-book-free-claim-evidence-genre_and_narrative_features"),
    );
    expect(await screen.findByTestId("whole-book-free-evidence-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-evidence-paragraph")).toHaveTextContent("踏入山门");
    fireEvent.click(screen.getByTestId("whole-book-free-open-in-reader"));
    await waitFor(() => {
      expect(screen.getByTestId("book-shell-toolbar")).toBeInTheDocument();
    });
  });

  it("shows entry label 查看分析进度 for running run", async () => {
    prepareSpy.mockResolvedValue(basePrepare({ latest_run: baseRun("running") }));
    renderPage("/books/1");
    await waitFor(() => {
      expect(screen.getByTestId("whole-book-free-entry")).toHaveTextContent("查看分析进度");
    });
  });
});

describe("wholeBookFreeEvidenceDeepLink stale handling", () => {
  it("rejects stale evidence for reader navigation", () => {
    expect(() =>
      openEvidenceInReader(1, { ...baseEvidenceSource(), state: "stale" }, 1),
    ).toThrow("EVIDENCE_STALE");
  });
});
