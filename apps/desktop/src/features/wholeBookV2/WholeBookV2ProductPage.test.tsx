import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import analysisFixture from "./fixtures/analysisV2.json";
import { WholeBookV2ProductPage } from "./WholeBookV2ProductPage";
import * as v2Api from "./api";
import * as freeApiMod from "../../services/wholeBookFreeProductApi";

const REANALYSE_CONSENT_TEXT =
  "我已了解重新分析会调用我配置的大模型 API，并可能产生模型费用。";

const productFlagState = vi.hoisted(() => ({ enabled: true }));
const realProviderState = vi.hoisted(() => ({ enabled: true }));

vi.mock("../../services/wholeBookFreeProductFlag", async () => {
  const actual = await vi.importActual<typeof import("../../services/wholeBookFreeProductFlag")>(
    "../../services/wholeBookFreeProductFlag",
  );
  return {
    ...actual,
    isWholeBookFreeProductEnabled: () => productFlagState.enabled,
  };
});

vi.mock("../../services/wholeBookRealProviderFlag", async () => {
  const actual = await vi.importActual<typeof import("../../services/wholeBookRealProviderFlag")>(
    "../../services/wholeBookRealProviderFlag",
  );
  return {
    ...actual,
    isWholeBookRealProviderEnabled: () => realProviderState.enabled,
  };
});

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    activeCloudProvider: vi.fn(async () => ({ provider_name: "deepseek" })),
  },
}));

const prepareSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "prepare");
const createRunSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "createRun");
const getV2Spy = vi.spyOn(v2Api, "getWholeBookV2");
const getProgressSpy = vi.spyOn(v2Api, "getWholeBookV2Progress");

const basePrepare = {
  book_id: 42,
  book_title: "余罪·V2验收样例",
  chapter_count: 36,
  character_count: 1683,
  mode: "free",
  mode_label: "原生全书分析",
  product_enabled: true,
  real_provider_enabled: true,
  run_creation_enabled: true,
  provider_available: true,
  active_provider_name: "deepseek",
  active_model_name: "deepseek-chat",
  context_safe: true,
  fixture_preview_enabled: false,
  recoverable_run: null,
  snapshot_rebuild_required: false,
  estimate: {
    estimate_id: 501,
    book_id: 42,
    mode: "free",
    estimated_windows: 12,
    estimated_provider_calls: 48,
    estimated_input_tokens: 120000,
    estimated_output_tokens: 32000,
    estimated_cost_min_cny: "2.50",
    estimated_cost_max_cny: "4.80",
    provider_name: "deepseek",
    model_name: "deepseek-chat",
    price_known: true,
    currency: "CNY",
  },
  recommended_limits: {
    max_provider_calls: 100,
    max_input_tokens: 200000,
    max_output_tokens: 50000,
    max_cost_budget_cny: "10.00",
  },
  blocking_reasons: [],
  warnings: [],
};

const completedV2Run = {
  run_id: 901,
  book_id: 42,
  status: "completed",
  mode: "free",
  engine_id: "hierarchical_v2",
  result_origin: "real_provider",
  snapshot_id: 1,
  started_at: null,
  completed_at: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/books/42/whole-book"]}>
        <Routes>
          <Route path="/books/:bookId/whole-book" element={<WholeBookV2ProductPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WholeBookV2ProductPage", () => {
  beforeEach(() => {
    productFlagState.enabled = true;
    realProviderState.enabled = true;
  });

  it("画像确认门：准备页打开即提示并禁用开始（CHG-20260815-095）", async () => {
    const profileApi = await import("../bookProfile/api");
    const spy = vi.spyOn(profileApi, "getBookProfile").mockResolvedValue(null);
    prepareSpy.mockResolvedValue({ ...basePrepare, latest_run: null, active_run: null } as never);
    try {
      renderPage();
      const gate = await screen.findByTestId("whole-book-v2-profile-gate");
      expect(gate).toHaveTextContent("先确认这本书的作品画像");
      // Confirming from here returns here, not to a chapter.
      expect(gate.querySelector("a")).toHaveAttribute(
        "href",
        "/books/42/profile?from=whole-book",
      );
      await waitFor(() =>
        expect(screen.getByRole("button", { name: /开始全书分析/ })).toBeDisabled(),
      );
    } finally {
      spy.mockRestore();
    }
  });

  it("开始按钮变灰时必须说出原因（缺一个勾也要说）", async () => {
    // 一个不说话的灰按钮，人只能盯着它猜。实测就发生过：后端每一项都是绿的，按钮却是灰的，
    // 而唯一的原因只是那条费用确认没勾——页面一个字都没说。
    const profileApi = await import("../bookProfile/api");
    vi.spyOn(profileApi, "getBookProfile").mockResolvedValue({
      status: "confirmed",
      axes: {},
      options: [],
      active_deltas: [],
    } as never);
    prepareSpy.mockResolvedValue({ ...basePrepare, latest_run: null, active_run: null } as never);
    renderPage();

    const reasons = await screen.findByTestId("whole-book-v2-start-blockers");
    expect(reasons).toHaveTextContent("请先勾选上面那条费用确认");
    expect(screen.getByRole("button", { name: /开始全书分析/ })).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/我已了解本次分析会调用/));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /开始全书分析/ })).toBeEnabled(),
    );
    // 能开始 ⇔ 一条原因都没有。两处逻辑分开写，这条断言把它们绑在一起。
    expect(screen.queryByTestId("whole-book-v2-start-blockers")).toBeNull();
  });

  it("服务商不可用时，按钮下面写的是后端给的那句原因", async () => {
    const profileApi = await import("../bookProfile/api");
    vi.spyOn(profileApi, "getBookProfile").mockResolvedValue({
      status: "confirmed",
      axes: {},
      options: [],
      active_deltas: [],
    } as never);
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: null,
      active_run: null,
      provider_available: false,
      run_creation_enabled: false,
      blocking_reasons: ["当前服务商 deepseek 未启用或已断开"],
    } as never);
    renderPage();

    const reasons = await screen.findByTestId("whole-book-v2-start-blockers");
    // 后端说的话原样呈现，不由客户端另编一句（INV-P4）。
    expect(reasons).toHaveTextContent("当前服务商 deepseek 未启用或已断开");
  });

  it("画像已确认时准备页没有门", async () => {
    const profileApi = await import("../bookProfile/api");
    const spy = vi.spyOn(profileApi, "getBookProfile").mockResolvedValue({
      status: "confirmed",
      axes: {},
      options: [],
      active_deltas: [],
    } as never);
    prepareSpy.mockResolvedValue({ ...basePrepare, latest_run: null, active_run: null } as never);
    try {
      renderPage();
      await screen.findByTestId("whole-book-v2-prepare");
      await waitFor(() =>
        expect(screen.queryByTestId("whole-book-v2-profile-gate")).not.toBeInTheDocument(),
      );
    } finally {
      spy.mockRestore();
    }
  });

  /** 只拆开篇。
   *
   *  扫榜要的是开篇：一次过十几本新书，只看前几章。实测同一本 542 章的书，整本 ¥2.90，
   *  前五章 ¥0.0285。一个不改变发出去什么的选项比没有更糟——用户以为省了钱，实际按整本付了，
   *  而这笔钱是他自己付给模型服务商的。
   */
  async function openPreparePanel(overrides: Record<string, unknown> = {}) {
    const profileApi = await import("../bookProfile/api");
    vi.spyOn(profileApi, "getBookProfile").mockResolvedValue({
      status: "confirmed",
      axes: {},
      options: [],
      active_deltas: [],
    } as never);
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: null,
      active_run: null,
      planner: "long_novel_engine",
      chapter_count: 542,
      ...overrides,
    } as never);
    renderPage();
    return screen.findByTestId("whole-book-v2-prepare");
  }

  it("长篇小说的准备页给出「读多少」，默认整本", async () => {
    await openPreparePanel();
    const scope = await screen.findByTestId("whole-book-v2-scope");
    expect(scope).toHaveTextContent("整本");
    expect(scope).toHaveTextContent("只拆开篇");
    // 全书章数照实说——这里写的是书有多长，不是这次要读多少。
    expect(scope).toHaveTextContent("542");
    expect(scope.querySelector<HTMLInputElement>('input[value="full"]')).toBeChecked();
  });

  it("选了开篇就按开篇重新报价", async () => {
    await openPreparePanel();
    const scope = await screen.findByTestId("whole-book-v2-scope");
    await waitFor(() => expect(prepareSpy).toHaveBeenCalled());
    // 默认不带范围＝整本。
    expect(prepareSpy.mock.calls.at(-1)?.[2] ?? null).toBeFalsy();

    fireEvent.click(scope.querySelector('input[value="opening"]') as HTMLInputElement);

    // 换了范围必须重新问价，否则面板上贴的还是整本的调用数和费用。
    await waitFor(() => expect(prepareSpy.mock.calls.at(-1)?.[2]).toBe(5));
  });

  it("短篇 / 读懂的书不给这个选择", async () => {
    // 「只拆开篇」在这两种情况下不是更便宜的选项，是没有意义的选项：
    // 读懂按节读，短篇本来就一次读完。
    await openPreparePanel({ planner: "hierarchical_v2" });
    await waitFor(() => expect(screen.queryByTestId("whole-book-v2-scope")).toBeNull());
  });

  it("拆文只在长篇引擎的书上可选", async () => {
    // The dispatcher drops the mode for a book the long-novel engine will not take, so a 拆文
    // request there spends a full run and returns a diagnostic. An option that cannot be
    // honoured must not look available.
    const profileApi = await import("../bookProfile/api");
    const spy = vi.spyOn(profileApi, "getBookProfile").mockResolvedValue({
      status: "confirmed",
      axes: {},
      options: [],
      active_deltas: [],
    } as never);
    try {
      prepareSpy.mockResolvedValue({
        ...basePrepare,
        planner: "hierarchical_v2",
        latest_run: null,
        active_run: null,
      } as never);
      renderPage();
      await screen.findByTestId("whole-book-v2-mode");
      const breakdown = () =>
        document.querySelector<HTMLInputElement>('input[value="story_breakdown"]')!;
      await waitFor(() => expect(breakdown().disabled).toBe(true));
      expect(document.querySelector<HTMLInputElement>('input[value="diagnostic"]')!.disabled).toBe(
        false,
      );

      cleanup();
      prepareSpy.mockResolvedValue({
        ...basePrepare,
        planner: "long_novel_engine",
        latest_run: null,
        active_run: null,
      } as never);
      renderPage();
      await screen.findByTestId("whole-book-v2-mode");
      await waitFor(() => expect(breakdown().disabled).toBe(false));
    } finally {
      spy.mockRestore();
    }
  });

  it("shows V2 nav labels when completed with v2 result", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);

    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
    });
    expect(screen.getByTestId("whole-book-v2-formal-page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /综合诊断/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /全书总览/ })).toBeInTheDocument();
    expect(screen.queryByText("DEV")).not.toBeInTheDocument();
    expect(getV2Spy).toHaveBeenCalled();
  });

  it("test_completed_v2_has_reanalyse_button", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-button")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "重新分析 V2" })).toBeInTheDocument();
  });

  it("test_reanalyse_opens_estimate_confirmation (no create until confirm)", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("whole-book-v2-reanalyse-button"));

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-confirm")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/重新分析会创建新的 V2 分析任务。当前分析结果不会立即删除/),
    ).toBeInTheDocument();
    expect(createRunSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => {
      expect(screen.queryByTestId("whole-book-v2-reanalyse-confirm")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
  });

  // 分析完之后，改读法没有入口：评测/拆文 的选择只在首次分析面板上，重新分析面板没有。
  // 更糟的是重新分析会按组件里那个默认值跑，也就是评测——一本按拆文分析过的书，会在没人
  // 被问过的情况下被重跑成评测。
  it("重新分析面板能改读法，且默认沿用这本已有的那一种", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue({
      ...analysisFixture,
      story_breakdown: {
        version: "1.0",
        availability: "available",
        four_beats: [
          { beat: "起", title: "开场", summary: "", chapter_start: 1, chapter_end: 2, evidence: [] },
        ],
        standout_moments: [],
        moment_count_rationale: "",
        chapter_hooks: [],
        reusable_techniques: [],
        supporting_cast: [],
        cast_note: "",
      },
    } as never);

    renderPage();
    await screen.findByTestId("whole-book-v2-reanalyse-button", undefined, { timeout: 5000 });
    fireEvent.click(screen.getByTestId("whole-book-v2-reanalyse-button"));

    const panel = await screen.findByTestId("whole-book-v2-reanalyse-confirm");
    const modes = within(panel).getByTestId("whole-book-v2-mode");
    const radios = within(modes).getAllByRole("radio") as HTMLInputElement[];
    const breakdown = radios.find((r) => r.value === "story_breakdown");
    const diagnostic = radios.find((r) => r.value === "diagnostic");

    // 这本的报告是拆文，所以重新分析默认还是拆文——不改读法的人不该被换掉读法。
    await waitFor(() => expect(breakdown!.checked).toBe(true));
    expect(diagnostic!.checked).toBe(false);

    // 而想换的人现在换得了。
    fireEvent.click(diagnostic!);
    expect(diagnostic!.checked).toBe(true);
  });

  // 一本书可以同时有评测和拆文，两者回答的不是同一个问题，谁也不替代谁。页面原先只能
  // 到达最后跑完的那一份，所以跑了第二种读法就等于把第一份藏起来——钱花了、结果存了、
  // 没有入口看。
  it("两种读法都在时给出切换入口，且能切过去", async () => {
    const breakdownRun = { ...completedV2Run, run_id: 77 };
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      completed_v2_runs_by_reading: {
        diagnostic: completedV2Run,
        story_breakdown: breakdownRun,
      },
      active_run: null,
    } as never);
    getV2Spy.mockImplementation(async (runId: number) =>
      runId === 77
        ? ({
            ...analysisFixture,
            story_breakdown: {
              version: "1.0",
              availability: "available",
              four_beats: [
                { beat: "起", title: "开场", summary: "", chapter_start: 1, chapter_end: 2, evidence: [] },
              ],
              standout_moments: [],
              moment_count_rationale: "",
              chapter_hooks: [],
              reusable_techniques: [],
              supporting_cast: [],
              cast_note: "",
            },
          } as never)
        : (analysisFixture as never),
    );

    renderPage();
    const sw = await screen.findByTestId("whole-book-v2-reading-switch", undefined, {
      timeout: 5000,
    });
    expect(within(sw).getByRole("button", { name: "评测" })).toBeInTheDocument();
    expect(within(sw).getByRole("button", { name: "拆文" })).toBeInTheDocument();

    // 默认停在最新那一份（评测），点「拆文」应当去取另一次运行的文档。
    fireEvent.click(within(sw).getByRole("button", { name: "拆文" }));
    await waitFor(() => expect(getV2Spy).toHaveBeenCalledWith(77));
    await waitFor(() => {
      const nav = screen.getByRole("navigation", { name: "全书分析模块" });
      expect(within(nav).getByRole("button", { name: /起承转合/ })).toBeInTheDocument();
    });
  });

  // 只有一种读法时不画开关：只有一个位置的开关不是开关。
  it("只有一种读法时没有切换入口", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      completed_v2_runs_by_reading: { diagnostic: completedV2Run },
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(analysisFixture as never);
    renderPage();
    await screen.findByTestId("whole-book-v2-report", undefined, { timeout: 5000 });
    expect(screen.queryByTestId("whole-book-v2-reading-switch")).not.toBeInTheDocument();
  });

  it("test_non_real_result_origin_shows_reanalysis_warning", async () => {
    const nonRealFixture = {
      ...analysisFixture,
      analysis_metadata: {
        ...analysisFixture.analysis_metadata,
        result_origin: "deterministic_test",
      },
      story: {
        ...analysisFixture.story,
        structure_stages: analysisFixture.story.structure_stages,
      },
    };

    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(nonRealFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-nonreal-warning")).toBeInTheDocument();
    });
    expect(
      screen.getByText("当前结果不是完整真实 V2 分析，需要重新分析。"),
    ).toBeInTheDocument();
  });

  it("test_old_result_preserved_while_new_run_running (banner + view old)", async () => {
    const activeRun = {
      run_id: 902,
      book_id: 42,
      status: "running",
      mode: "free",
      engine_id: "hierarchical_v2",
      result_origin: "real_provider",
      snapshot_id: 1,
      started_at: null,
      completed_at: null,
    };

    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: activeRun,
      active_run: activeRun,
      completed_v2_run: completedV2Run,
    } as never);

    getV2Spy.mockResolvedValue(analysisFixture as never);
    getProgressSpy.mockResolvedValue({
      schema_version: "whole-book-progress-v2.0",
      overall_percent: 35,
      current_stage: "extract_windows",
      stage_percent: 50,
      current_window: 3,
      total_windows: 12,
      current_chapter: 10,
      total_chapters: 36,
      provider_calls_completed: 5,
      provider_calls_estimated: 48,
      successful_calls: 5,
      failed_calls: 0,
      retry_calls: 0,
      repair_calls: 0,
      elapsed_seconds: 120,
      estimated_remaining_seconds: 300,
      estimated_cost: 1.2,
      estimated_actual_cost: 0.8,
      provider: "deepseek",
      model: "deepseek-chat",
      last_completed_action: "抽取窗口",
      current_action: "抽取窗口 3/12",
      last_activity_at: "2026-08-10T10:00:00Z",
    } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-running-banner")).toBeInTheDocument();
    });
    expect(screen.getByText("新的 V2 分析正在进行")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-progress")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "查看当前旧结果" }));

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("whole-book-v2-progress")).not.toBeInTheDocument();
    expect(getV2Spy).toHaveBeenCalledWith(901);
  });

  it("mock createRun asserts reanalyse/force flags and NEW client_request_id", async () => {
    const requestIds: string[] = [];
    createRunSpy.mockImplementation(async (_bookId, body) => {
      requestIds.push(body.client_request_id);
      return {
        run: {
          run_id: 903,
          book_id: 42,
          status: "running",
          mode: "free",
          engine_id: "hierarchical_v2",
          result_origin: "real_provider",
          snapshot_id: 1,
          started_at: null,
          completed_at: null,
        },
      } as never;
    });

    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("whole-book-v2-reanalyse-button"));

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-confirm")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("whole-book-v2-force-full"));
    fireEvent.click(screen.getByRole("checkbox", { name: REANALYSE_CONSENT_TEXT }));
    fireEvent.click(screen.getByRole("button", { name: "确认开始重新分析" }));

    await waitFor(() => {
      expect(createRunSpy).toHaveBeenCalledTimes(1);
    });

    const call = createRunSpy.mock.calls[0];
    expect(call[0]).toBe(42);
    const body = call[1];
    expect(body.reanalyse).toBe(true);
    expect(body.force_full_reanalysis).toBe(true);
    expect(body.previous_run_id).toBe(901);
    expect(body.client_request_id).toBeTruthy();
    expect(typeof body.client_request_id).toBe("string");
    expect(requestIds).toHaveLength(1);
  });

  it("shows legacy notice when v2 returns 404", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      book_title: "旧版书",
      latest_run: {
        run_id: 902,
        book_id: 42,
        status: "completed",
        mode: "free",
        engine_id: "legacy",
        result_origin: "legacy",
        snapshot_id: 1,
        started_at: null,
        completed_at: null,
      },
      completed_v2_run: null,
      // 旧结果是从这个字段读的，不是从 latest_run 推的——后端对一本旧书返回的正是它。
      // 这条用例的桩一直没给它，于是页面正确地停在准备页，用例却以为是页面坏了。
      non_real_completed_v2_run: {
        run_id: 902,
        book_id: 42,
        status: "completed",
        mode: "free",
        engine_id: "legacy",
        result_origin: "legacy",
        snapshot_id: 1,
        started_at: null,
        completed_at: null,
      },
      active_run: null,
    } as never);

    const { ApiError } = await import("../../services/apiClient");
    getV2Spy.mockRejectedValue(
      new ApiError("WHOLE_BOOK_V2_RESULT_NOT_FOUND", "V2 result is not available", 404, {
        error_code: "WHOLE_BOOK_V2_RESULT_NOT_FOUND",
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-legacy-notice")).toBeInTheDocument();
    });
    expect(
      screen.getByText("这是旧版全书分析结果，需要重新分析以生成 V2 完整结果。"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-v2-report")).not.toBeInTheDocument();
  });

  it("does not fall back to mock fixture on non-404 API failure", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      book_title: "错误书",
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);

    const { ApiError } = await import("../../services/apiClient");
    getV2Spy.mockRejectedValue(new ApiError("INTERNAL_ERROR", "服务器错误", 500, {}));

    renderPage();

    await waitFor(() => {
      expect(screen.queryByTestId("whole-book-v2-report")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("余罪·V2验收样例")).not.toBeInTheDocument();
  });
});
