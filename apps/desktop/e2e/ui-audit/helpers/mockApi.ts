/**
 * Deterministic Mock API for StoryLens UI audit screenshots.
 * Never returns real user data or live API keys.
 */

import type { Page, Route } from "@playwright/test";
import { buildVisualizationFixture, buildChapterParagraphs } from "../../fixtures/readerJourneyE2eFixtures";

export type ProviderKind =
  | "connected"
  | "disconnected"
  | "disabled"
  | "invalid_cred"
  | "unknown_cred"
  | "none";

export type MockScenario = {
  books?: "empty" | "one" | "multi" | "long_titles";
  /** Empty chapter list for a book that exists — product no-chapter reading state. */
  chapters?: "default" | "empty";
  provider?: ProviderKind;
  cloudEnabled?: boolean;
  multiProviders?: boolean;
  tasks?: "empty" | "one_running" | "multi" | "long";
  chapterMode?: "default" | "short" | "long" | "empty" | "loading" | "long_title";
  analysisRun?: "none" | "running" | "failed" | "succeeded" | "budget_pause";
  journey?: "none" | "generating" | "ready" | "failed" | "empty";
  importPreview?:
    | "ok"
    | "suspect"
    | "format_error"
    | "too_large"
    | "encoding_error"
    | "pending"
    | "duplicate_on_upload";
  aiSetup?: "ok" | "fail" | "pending" | "needs_repair";
  delayMs?: number;
  paragraphsDelayMs?: number;
  healthOk?: boolean;
};

const MASKED_KEY_HINT = "sk-audit-****MASKED****";

export function connectedProvider(overrides: Record<string, unknown> = {}) {
  return {
    capability_schema_version: "1c-a-2",
    name: "aliyun_qwen_plus",
    default_model: "qwen3.7-plus",
    enabled: true,
    healthy: true,
    configured: true,
    connected: true,
    status: "ready",
    eligible_for_automatic_analysis: false,
    supports_boundary_candidates: true,
    requires_boundary_review: true,
    automatic_boundary_routing: false,
    manual_boundary_candidate_eligible: true,
    automatic_route_eligible: false,
    manual_short_task_eligible: false,
    manual_selection_blockers: [],
    automatic_route_blockers: ["auto_route_disabled"],
    allow_auto_route: false,
    eligibility_status: "eligible",
    evaluated_at: "2026-07-20T00:00:00Z",
    health_state: "healthy",
    health_source: "configured_readiness",
    health_checked_at: "2026-07-20T00:00:00Z",
    provider_state_version: "state-audit-1",
    capabilities: {
      enabled: true,
      cloud: true,
      region: "cn-beijing",
      default: false,
      manual_only: false,
      structured_output_mode: "json_object",
      sends_content_to_cloud: true,
      profile_name: "aliyun_qwen_plus",
      supports_boundary_candidates: true,
      requires_boundary_review: true,
      automatic_boundary_routing: false,
    },
    workflow_prompts: {
      boundary_candidate: "v3.5",
      boundary_adjudication: "v1",
      scene_analysis: "v3.1",
      thinking: false,
      boundary_confirmation: "human_required",
    },
    ...overrides,
  };
}

function providerList(scenario: MockScenario) {
  const kind = scenario.provider ?? "connected";
  if (kind === "none") return [];

  const cloudEnabled = scenario.cloudEnabled ?? true;
  const base = connectedProvider();
  let primary = base;
  if (kind === "disconnected") {
    primary = connectedProvider({
      configured: false,
      connected: false,
      healthy: false,
      enabled: false,
      health_state: "unhealthy",
      manual_boundary_candidate_eligible: false,
      manual_selection_blockers: ["provider_not_configured", "credential_missing"],
      eligibility_status: "blocked",
    });
  } else if (kind === "disabled") {
    primary = connectedProvider({
      enabled: false,
      connected: false,
      healthy: false,
      eligibility_status: "blocked",
      manual_boundary_candidate_eligible: false,
      manual_selection_blockers: ["provider_disabled"],
    });
  } else if (kind === "invalid_cred") {
    primary = connectedProvider({
      configured: true,
      connected: false,
      healthy: false,
      health_state: "unhealthy",
      eligibility_status: "blocked",
      manual_boundary_candidate_eligible: false,
      manual_selection_blockers: ["credential_invalid"],
    });
  } else if (kind === "unknown_cred") {
    primary = connectedProvider({
      configured: true,
      connected: false,
      healthy: false,
      health_state: "unknown",
      eligibility_status: "unknown",
      manual_boundary_candidate_eligible: false,
    });
  }

  if (!cloudEnabled && kind === "connected") {
    primary = connectedProvider({
      ...primary,
      eligibility_status: "blocked",
      manual_boundary_candidate_eligible: false,
      manual_selection_blockers: ["cloud_master_switch_off"],
    });
  }

  if (!scenario.multiProviders) return [primary];
  return [
    primary,
    connectedProvider({
      name: "aliyun_qwen_max",
      default_model: "qwen3.7-max",
      capabilities: { ...base.capabilities, profile_name: "aliyun_qwen_max" },
    }),
  ];
}

function booksPayload(scenario: MockScenario) {
  const mode = scenario.books ?? "one";
  if (mode === "empty") return [];
  const one = {
    id: 1,
    title: "虚构星港编年史",
    source_file_name: "fiction_starport.txt",
    source_file_hash: "audit-hash-0001",
    created_at: "2026-07-01T08:00:00Z",
  };
  if (mode === "one") return [one];
  if (mode === "long_titles") {
    return [
      {
        ...one,
        title:
          "虚构超长书名：当星港的潮汐钟敲响第三千次时守夜人仍在抄写无人阅读的编年史与被遗忘的航线图",
      },
    ];
  }
  return [
    one,
    {
      id: 2,
      title: "虚构潮汐图书馆",
      source_file_name: "fiction_tides.docx",
      source_file_hash: "audit-hash-0002",
      created_at: "2026-07-02T08:00:00Z",
    },
    {
      id: 3,
      title: "虚构玻璃鸟",
      source_file_name: "fiction_bird.epub",
      source_file_hash: "audit-hash-0003",
      created_at: "2026-07-03T08:00:00Z",
    },
  ];
}

function chaptersPayload(scenario: MockScenario) {
  if (scenario.chapters === "empty") return [];
  const longTitle =
    scenario.chapterMode === "long_title"
      ? "第一章　虚构超长章节名：守夜人沿着螺旋阶梯下降到潮汐钟房并抄写三百年无人核对的航线附录"
      : "第一章　潮汐钟";
  return [
    {
      id: 1,
      book_id: 1,
      chapter_index: 1,
      section_type: "chapter",
      title: longTitle,
      display_title: longTitle,
    },
    {
      id: 2,
      book_id: 1,
      chapter_index: 2,
      section_type: "chapter",
      title: "第二章　星港夜航",
      display_title: "第二章　星港夜航",
    },
  ];
}

/** Matches backend SceneResponse / frontend Scene for GET /chapters/{id}/scenes. */
function scenesPayload() {
  return [
    {
      id: 1,
      scene_key: "B0001-C0001-R0001-S0001",
      book_id: 1,
      chapter_id: 1,
      ordinal: 1,
      start_paragraph_id: "B0001-C0001-P0001",
      end_paragraph_id: "B0001-C0001-P0002",
      created_by_run_id: 55,
      boundary_detected: true,
      boundary_confidence: 0.92,
    },
    {
      id: 2,
      scene_key: "B0001-C0001-R0001-S0002",
      book_id: 1,
      chapter_id: 1,
      ordinal: 2,
      start_paragraph_id: "B0001-C0001-P0003",
      end_paragraph_id: "B0001-C0001-P0003",
      created_by_run_id: 55,
      boundary_detected: false,
      boundary_confidence: 0.4,
    },
  ];
}

function paragraphsPayload(scenario: MockScenario) {
  const mode = scenario.chapterMode ?? "default";
  if (mode === "empty") return { items: [] };
  if (mode === "short") {
    return {
      items: [
        {
          id: "B0001-C0001-P0001",
          chapter_id: 1,
          paragraph_index: 1,
          raw_text: "虚构短章：守夜人点燃一盏油灯。",
        },
      ],
    };
  }
  if (mode === "long") {
    const items = Array.from({ length: 80 }, (_, i) => ({
      id: `B0001-C0001-P${String(i + 1).padStart(4, "0")}`,
      chapter_id: 1,
      paragraph_index: i + 1,
      raw_text: `虚构长章段落 ${i + 1}：潮汐钟的声音在石廊里回荡，抄写员继续誊录无人阅读的航线。`,
    }));
    return { items };
  }
  const built = buildChapterParagraphs();
  if (Array.isArray(built) && built.length) {
    return {
      items: built,
      offset: 0,
      limit: 500,
      total: built.length,
      has_more: false,
    };
  }
  return {
    items: [
      {
        id: "B0001-C0001-P0001",
        chapter_id: 1,
        paragraph_index: 1,
        raw_text: "虚构正文：守夜人推开潮汐钟房的门，空气里有旧纸与海盐的味道。",
      },
      {
        id: "B0001-C0001-P0002",
        chapter_id: 1,
        paragraph_index: 2,
        raw_text: "他摊开编年史，准备抄写今晚的航线记录。",
      },
      {
        id: "B0001-C0001-P0003",
        chapter_id: 1,
        paragraph_index: 3,
        raw_text: "窗外星港灯火次第亮起，像一张缓慢展开的地图。",
      },
    ],
    offset: 0,
    limit: 500,
    total: 3,
    has_more: false,
  };
}

function tasksPayload(scenario: MockScenario) {
  const mode = scenario.tasks ?? "multi";
  if (mode === "empty") return [];
  const mk = (
    id: number,
    status: string,
    title: string,
    extra: Record<string, unknown> = {},
  ) => ({
    id,
    subject_id: "1",
    book_id: 1,
    chapter_id: 1,
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    status,
    progress_current: status === "succeeded" ? 1 : status === "running" ? 1 : 0,
    progress_total: 3,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: status === "failed",
    current_stage: status === "succeeded" ? "completed" : "scene_analysis",
    created_at: "2026-07-10T08:00:00Z",
    updated_at: "2026-07-10T09:00:00Z",
    display_title: title,
    error_code: status === "failed" ? "SCENE_PIPELINE_FAILED" : null,
    error_message: status === "failed" ? "审计模拟：模型调用失败（Fake）" : null,
    root_error_message: status === "failed" ? "审计模拟：模型调用失败（Fake）" : null,
    failed_stage: status === "failed" ? "scene_analysis" : null,
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    ...extra,
  });
  if (mode === "one_running") {
    return [mk(101, "running", "虚构星港编年史 · 第一章")];
  }
  const base = [
    mk(101, "queued", "等待中的任务", { progress_current: 0, progress_total: 3 }),
    mk(102, "running", "运行中的任务", { progress_current: 1, progress_total: 3 }),
    mk(103, "succeeded", "已完成的任务", {
      progress_current: 3,
      progress_total: 3,
      total_scene_count: 3,
      completed_scene_count: 3,
    }),
    mk(104, "failed", "已失败的任务", {
      progress_current: 1,
      progress_total: 3,
      total_scene_count: 3,
      completed_scene_count: 1,
      remaining_scene_count: 2,
      failed_scene_id: 2,
      failed_scene_index: 1,
      failed_invocation_id: 9001,
      scene_validation_detail: {
        validation_error_message: "审计模拟：证据段落越界",
        allowed_paragraph_ids: ["B0001-C0001-P0001"],
        illegal_evidence_ids: [
          { field_path: "goal.evidence", paragraph_id: "B0001-C0001-P0099" },
        ],
      },
      failed_invocation: {
        id: 9001,
        http_status_code: 422,
        error_message: "审计模拟 Invocation 失败",
        latency_ms: 120,
        total_tokens: 40,
      },
    }),
    mk(105, "cancelled", "已取消的任务", { progress_current: 0, progress_total: 3 }),
  ];
  if (mode === "long") {
    return [
      ...base,
      ...Array.from({ length: 12 }, (_, i) =>
        mk(200 + i, i % 2 === 0 ? "succeeded" : "failed", `长列表任务 ${i + 1}`),
      ),
    ];
  }
  return base;
}

function analysisRunPayload(scenario: MockScenario) {
  const mode = scenario.analysisRun ?? "none";
  if (mode === "none") return null;
  const status =
    mode === "budget_pause" ? "aborted_by_limit" : mode === "succeeded" ? "succeeded" : mode;
  return {
    id: 55,
    subject_id: "1",
    book_id: 1,
    chapter_id: 1,
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    status,
    progress_current: mode === "running" ? 1 : mode === "succeeded" ? 3 : 0,
    progress_total: 3,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: mode === "failed",
    current_stage:
      mode === "succeeded"
        ? "completed"
        : mode === "running"
          ? "scene_analysis"
          : mode === "budget_pause"
            ? "scene_analysis_budget"
            : "failed",
    created_at: "2026-07-10T08:00:00Z",
    updated_at: "2026-07-10T09:00:00Z",
    total_scene_count: 3,
    completed_scene_count: mode === "succeeded" ? 3 : mode === "running" ? 1 : 0,
    error_message: mode === "failed" ? "审计模拟失败：Fake Provider 拒绝" : null,
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
  };
}

function runResultsPayload() {
  return {
    run: {
      id: 55,
      status: "succeeded",
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      prompt_version: "v3.5",
      schema_version: "1",
      analysis_mode: "assisted_boundary_review",
      execution_mode: "cloud",
      completed_at: "2026-07-10T09:00:00Z",
    },
    chapter: {
      id: 1,
      book_id: 1,
      chapter_index: 1,
      title: "第一章　潮汐钟",
      display_title: "第一章　潮汐钟",
    },
    boundary_revision: {
      id: 1,
      revision_number: 1,
      coverage_rate: 1,
      confirmed_by: "audit",
      confirmed_at: "2026-07-10T08:30:00Z",
    },
    summary: {
      total_scene_count: 2,
      single_paragraph_scene_count: 1,
      longest_scene_ordinal: 1,
      longest_scene_paragraph_count: 2,
      manual_added_boundary_count: 0,
      model_accepted_boundary_count: 1,
      user_accepted_conflict_count: 0,
      artifact_coverage_rate: 1,
      evidence_coverage_rate: 1,
      offline_recovered_scene_count: 0,
    },
    scenes: [
      {
        scene: {
          id: 1,
          scene_key: "B0001-C0001-R0001-S0001",
          ordinal: 1,
          start_paragraph_id: "B0001-C0001-P0001",
          end_paragraph_id: "B0001-C0001-P0002",
          paragraph_count: 2,
          is_single_paragraph: false,
          boundary_source: "model_accepted",
          boundary_revision_id: 1,
          boundary_detected: true,
          boundary_confidence: 0.9,
        },
        analysis_artifact: {
          id: 101,
          schema_version: "v1",
          prompt_version: "v3.1",
          provider: "aliyun_qwen_plus",
          model: "qwen3.7-plus",
          confidence: 0.8,
          validation_status: "valid",
          created_at: "2026-07-10T09:00:00Z",
          offline_recovered: false,
          analysis: {
            scene_id: "B0001-C0001-R0001-S0001",
            entry_state: {
              summary: "守夜人进入潮汐钟房",
              evidence_paragraph_ids: ["B0001-C0001-P0001"],
            },
            goal: {
              summary: "抄写今晚航线",
              evidence_paragraph_ids: ["B0001-C0001-P0001"],
            },
            obstacle: { summary: "", evidence_paragraph_ids: [] },
            key_actions: [
              {
                summary: "摊开编年史",
                evidence_paragraph_ids: ["B0001-C0001-P0002"],
              },
            ],
            turning_point: { summary: "", evidence_paragraph_ids: [] },
            outcome: {
              summary: "开始誊录",
              evidence_paragraph_ids: ["B0001-C0001-P0002"],
            },
            unresolved_question: { summary: "", evidence_paragraph_ids: [] },
            function_tags: ["事件推进"],
            confidence: 0.8,
          },
        },
        evidence: [],
        illegal_evidence: [],
        revision: null,
      },
    ],
  };
}

function aiSetupResponse(scenario: MockScenario, persist: boolean) {
  const mode = scenario.aiSetup ?? "ok";
  if (mode === "fail") {
    return {
      ok: false,
      user_message: "模型服务验证失败\nAPI Key 无效或模型服务拒绝了请求。",
      persisted: false,
      credential_configured: false,
      provider_enabled: false,
      cloud_enabled: false,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "failed",
      analysis_mode: null,
      blockers: ["connection_test_failed"],
      needs_cloud_consent: false,
      error_code: "CREDENTIAL_INVALID",
      model_service_validated: false,
      analysis_ready: false,
      readiness_reasons: ["API Key 无效或已失效"],
    };
  }
  if (mode === "needs_repair") {
    return {
      ok: false,
      user_message: "旧配置需要修复：请重新输入 API Key 并确认正文发送。",
      persisted: false,
      credential_configured: true,
      provider_enabled: false,
      cloud_enabled: true,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "needs_repair",
      analysis_mode: "BALANCED",
      blockers: ["credential_stale"],
      needs_cloud_consent: true,
      error_code: "CONFIG_NEEDS_REPAIR",
      model_service_validated: false,
      analysis_ready: false,
      readiness_reasons: ["配置需要修复"],
    };
  }
  return {
    ok: true,
    user_message: persist
      ? "配置完成。模型服务、计价和预算检查均已通过，可以开始分析。"
      : "API Key 与模型服务验证成功。验证成功，保存配置后还需检查分析预算和计价信息。",
    persisted: persist,
    credential_configured: true,
    provider_enabled: persist,
    cloud_enabled: persist,
    provider_eligible: persist,
    selected_provider_id: "aliyun_qwen_plus",
    connection_status: persist ? "connected" : "tested",
    analysis_mode: "BALANCED",
    blockers: [],
    needs_cloud_consent: false,
    error_code: null,
    model_service_validated: true,
    analysis_ready: persist,
    readiness_reasons: persist ? [] : ["API Key 尚未保存"],
  };
}

function importPreview(scenario: MockScenario) {
  const mode = scenario.importPreview ?? "ok";
  if (mode === "format_error") {
    return { status: 400, body: { detail: "不支持的文件格式（审计 Mock）" } };
  }
  if (mode === "too_large") {
    return { status: 413, body: { detail: "文件过大（审计 Mock）" } };
  }
  if (mode === "encoding_error") {
    return { status: 400, body: { detail: "无法识别文本编码（审计 Mock）" } };
  }
  if (mode === "suspect") {
    return {
      status: 200,
      body: {
        encoding: "utf-8",
        byte_count: 12_000_000,
        candidate_count: 1,
        final_chapter_count: 1,
        chapter_titles: ["全文"],
        warning: "CHAPTER_DETECTION_SUSPECT",
      },
    };
  }
  return {
    status: 200,
    body: {
      encoding: "utf-8",
      byte_count: 48_000,
      candidate_count: 3,
      final_chapter_count: 3,
      chapter_titles: ["第一章　潮汐钟", "第二章　星港夜航", "第三章　玻璃鸟"],
      warning: null,
    },
  };
}

const budget = {
  cloud_request_budget_enabled: true,
  cloud_max_input_tokens_per_request: 16000,
  cloud_max_output_tokens_per_request: 2000,
  cloud_max_requests_per_run: 10,
  cloud_daily_request_limit: 30,
  cloud_daily_token_limit: 200000,
  cloud_daily_estimated_cost_limit: 5,
  currency: "CNY",
  cloud_stop_on_unknown_pricing: true,
  cloud_confirm_each_paid_test: true,
};

const preflight = {
  eligible: true,
  provider_state_version: "state-audit-1",
  within_budget: true,
  exceeded_dimensions: [],
  paragraph_count: 24,
  transition_count: 23,
  detection_batch_count: 2,
  adjudication_batch_count_estimated: 1,
  expected_request_count: 3,
  worst_case_request_count: 6,
  estimated_total_tokens: 1200,
  worst_case_total_tokens: 2400,
  estimated_cost: 0.02,
  worst_case_cost: 0.04,
  currency: "CNY",
  remaining: { requests: 70, tokens: 90000, estimated_cost: 2.5 },
};

export async function installUiAuditMocks(page: Page, scenario: MockScenario = {}) {
  await page.unroute("**/api/v1/**").catch(() => undefined);
  await page.unroute("**/health").catch(() => undefined);

  const cloudEnabled = scenario.cloudEnabled ?? true;
  const providers = providerList(scenario);
  const books = booksPayload(scenario);
  const delay = scenario.delayMs ?? 0;

  await page.route("**/health", async (route) => {
    if (scenario.healthOk === false) {
      return route.abort("connectionfailed");
    }
    return route.fulfill({ json: { status: "ok", database: "ok" } });
  });

  await page.route("**/api/v1/**", async (route: Route) => {
    if (delay > 0) await new Promise((r) => setTimeout(r, delay));
    const url = route.request().url();
    const method = route.request().method();

    if (scenario.healthOk === false && url.includes("/books") && method === "GET") {
      return route.abort("connectionfailed");
    }
    if (url.includes("/desktop/ai-setup/recommended-qwen")) {
      if (method === "GET") {
        return route.fulfill({ json: aiSetupResponse(scenario, true) });
      }
      let persist = false;
      try {
        const body = route.request().postDataJSON() as { persist?: boolean };
        persist = Boolean(body?.persist);
      } catch {
        persist = false;
      }
      if (scenario.aiSetup === "pending") {
        // Delay then fulfill once — avoid double-handle after abort.
        await new Promise((r) => setTimeout(r, 600));
      }
      try {
        return await route.fulfill({ json: aiSetupResponse(scenario, persist) });
      } catch {
        return;
      }
    }

    if (url.includes("/model-providers") && url.includes("/configuration")) {
      const kind = scenario.provider ?? "connected";
      return route.fulfill({
        json: {
          display_name: "阿里云百炼",
          plus_model: "qwen3.7-plus",
          max_model: "qwen3.7-max",
          flash_model: "qwen3.6-flash",
          credential_state:
            kind === "disconnected"
              ? "missing"
              : kind === "unknown_cred"
                ? "unknown"
                : kind === "invalid_cred"
                  ? "invalid"
                  : "configured",
          enabled: kind !== "disabled" && kind !== "disconnected" && kind !== "none",
          disconnected: kind === "disconnected" || kind === "invalid_cred",
          connection_state:
            kind === "connected" ? "connected" : kind === "unknown_cred" ? "unknown" : "disconnected",
          workspace_id: "ws-audit",
          base_url: "https://example.invalid",
          region: "cn-beijing",
          timeout_seconds: 300,
          max_retries: 3,
          // Never expose real keys — only a masked hint string if UI echoes it.
          api_key_masked: MASKED_KEY_HINT,
        },
      });
    }

    if (url.includes("/model-providers") && url.includes("transport")) {
      return route.fulfill({
        json: {
          ok: (scenario.provider ?? "connected") === "connected",
          message:
            (scenario.provider ?? "connected") === "connected"
              ? "传输诊断成功（审计 Mock）"
              : "传输诊断失败（审计 Mock）",
        },
      });
    }

    if (url.includes("/model-providers") && method === "GET") {
      return route.fulfill({ json: providers });
    }

    if (url.includes("/settings/cloud-budget")) {
      return route.fulfill({ json: budget });
    }
    if (url.includes("/settings/cloud")) {
      return route.fulfill({
        json: {
          enabled: cloudEnabled,
          state: cloudEnabled ? "enabled" : "disabled",
        },
      });
    }
    if (url.includes("/cloud-usage")) {
      return route.fulfill({
        json: {
          request_count: 3,
          input_tokens: 12000,
          output_tokens: 3000,
          total_tokens: 15000,
          estimated_cost: 0.12,
          remaining_estimated_cost: 4.88,
          blocked_reasons: cloudEnabled ? [] : ["云端总开关已关闭"],
        },
      });
    }
    if (url.includes("/cloud-pricing")) {
      return route.fulfill({
        json: { configured: true, valid: true, enabled: true, pricing_version: "v1-audit" },
      });
    }
    if (url.includes("/system/diagnostics")) {
      return route.fulfill({ json: { fastapi: "ok", sqlite: "ok", python: "3.11" } });
    }
    if (url.includes("/settings/desktop")) {
      return route.fulfill({ json: { demo_mode: true, theme: "light" } });
    }
    if (url.includes("/model-routing")) {
      return route.fulfill({
        json: [
          {
            task: "scene_analysis",
            provider: "aliyun_qwen_plus",
            model: "qwen3.7-plus",
            reason: "审计 Mock 路由",
          },
        ],
      });
    }

    if (
      url.includes("chapter-detection/preview") ||
      url.includes("/reparse-preview") ||
      url.includes("reparse-with-file-preview") ||
      (url.includes("/books") && url.includes("preview"))
    ) {
      if (scenario.importPreview === "pending") {
        await new Promise((r) => setTimeout(r, 800));
      }
      if (url.includes("reparse-with-file-preview") || url.includes("/reparse-preview")) {
        const titles = Array.from({ length: 24 }, (_, i) => `第${i + 1}章　虚构章节标题 ${i + 1}`);
        return route.fulfill({
          json: {
            hash_match: true,
            old_chapter_count: 2,
            old_paragraph_count: 40,
            formal_chapter_count: titles.length,
            front_matter_count: 0,
            new_paragraph_count: 480,
            chapter_titles: titles,
            middle_sample_titles: [titles[11]],
            ending_sample_titles: [titles[titles.length - 1]],
            has_succeeded_runs: false,
          },
        });
      }
      const preview = importPreview(scenario);
      return route.fulfill({ status: preview.status, json: preview.body });
    }

    if (url.includes("/books/import") && method === "POST") {
      if (scenario.importPreview === "duplicate_on_upload") {
        return route.fulfill({
          status: 409,
          json: {
            detail: {
              error_code: "DUPLICATE_BOOK",
              message: "该文件已导入",
              details: {},
            },
          },
        });
      }
      return route.fulfill({
        status: 201,
        json: {
          book_id: 99,
          status: "imported",
          chapter_count: 3,
          paragraph_count: 40,
          warning: null,
        },
      });
    }

    if (
      (url.endsWith("/books") || url.endsWith("/books/")) &&
      method === "POST"
    ) {
      return route.fulfill({
        json: {
          id: 99,
          title: "新导入虚构文本",
          source_file_name: "fiction_new.txt",
          source_file_hash: "audit-hash-new",
          created_at: "2026-07-20T12:00:00Z",
        },
      });
    }

    if (url.match(/\/books\/?\d*$/) && !url.includes("chapters") && method === "GET") {
      if (url.endsWith("/books") || url.endsWith("/books/")) {
        return route.fulfill({ json: books });
      }
      const id = Number(url.split("/books/")[1]?.split(/[?#]/)[0] || "1");
      const found = books.find((b) => b.id === id) ?? books[0] ?? {
        id,
        title: "虚构星港编年史",
        source_file_name: "fiction_starport.txt",
        source_file_hash: "audit-hash-0001",
        created_at: "2026-07-01T08:00:00Z",
      };
      return route.fulfill({ json: found });
    }

    if (
      url.includes("/chapters") &&
      !url.includes("/scenes") &&
      !url.includes("paragraphs") &&
      method === "GET"
    ) {
      return route.fulfill({ json: chaptersPayload(scenario) });
    }

    if (url.includes("/paragraphs")) {
      const pDelay = scenario.paragraphsDelayMs ?? 0;
      if (scenario.chapterMode === "loading" || pDelay > 0) {
        await new Promise((r) => setTimeout(r, pDelay || 4000));
      }
      return route.fulfill({ json: paragraphsPayload(scenario) });
    }

    if (url.includes("preflight") || (url.includes("budget") && url.includes("analysis"))) {
      return route.fulfill({
        json: {
          ...preflight,
          eligible: (scenario.provider ?? "connected") === "connected" && cloudEnabled,
        },
      });
    }

    if (url.includes("/model-invocations")) {
      return route.fulfill({
        json: [
          {
            id: 9001,
            run_id: 104,
            http_status_code: 422,
            error_message: "审计模拟 Invocation 失败",
            latency_ms: 120,
            total_tokens: 40,
          },
        ],
      });
    }

    if (url.includes("/results")) {
      return route.fulfill({ json: runResultsPayload() });
    }

    if (url.includes("/analysis-runs") && method === "GET") {
      const singleRunMatch = url.match(/\/analysis-runs\/(\d+)(?:\?|$)/);
      if (singleRunMatch && !url.includes("/results") && !url.includes("reader-journey")) {
        const runId = Number(singleRunMatch[1]);
        const fromTasks = tasksPayload({ ...scenario, tasks: scenario.tasks ?? "multi" });
        const found = fromTasks.find((item) => item.id === runId);
        const fromPayload = analysisRunPayload(scenario);
        const run =
          found ||
          (fromPayload
            ? { ...fromPayload, id: runId }
            : {
                id: runId,
                subject_id: "1",
                book_id: 1,
                chapter_id: 1,
                provider: "aliyun_qwen_plus",
                model: "qwen3.7-plus",
                status: "succeeded",
                progress_current: 3,
                progress_total: 3,
                execution_mode: "cloud",
                cloud_consent: true,
                sends_content_to_cloud: true,
                retryable: false,
                created_at: "2026-07-10T08:00:00Z",
                reusable_checkpoint_count: 0,
                conflicted_checkpoint_count: 0,
                checkpoint_total_count: 0,
                checkpoint_available: false,
              });
        return route.fulfill({ json: run });
      }
      // list only: /analysis-runs or /analysis-runs?
      if (/\/analysis-runs\/?(?:\?|$)/.test(url)) {
        if ((scenario.tasks ?? "multi") !== "empty" || scenario.analysisRun !== "none") {
          const fromTasks = tasksPayload({ ...scenario, tasks: scenario.tasks ?? "multi" });
          if (fromTasks.length) return route.fulfill({ json: fromTasks });
        }
        const single = analysisRunPayload(scenario);
        return route.fulfill({ json: single ? [single] : [] });
      }
    }

    if (url.includes("/reader-journey") || url.includes("journey")) {
      const j = scenario.journey ?? "ready";
      const isProgress =
        url.includes("/progress") || /\/reader-journey-runs\/\d+/.test(url);
      if (j === "none") {
        return route.fulfill({ status: 404, json: { detail: "not generated" } });
      }
      if (j === "generating") {
        if (isProgress) {
          return route.fulfill({
            json: {
              journey_run_id: 701,
              analysis_run_id: 55,
              status: "scene_profiles_running",
              total_scene_count: 14,
              completed_scene_count: 7,
              remaining_scene_count: 7,
              phase_count: 0,
              has_chapter_summary: false,
              retryable: true,
              progress_percent: 55,
            },
          });
        }
        return route.fulfill({
          json: {
            journey_run_id: 701,
            analysis_run_id: 55,
            status: "running",
            progress_percent: 55,
            message: "正在生成 Reader Journey（审计）",
          },
        });
      }
      if (j === "failed") {
        if (isProgress) {
          return route.fulfill({
            json: {
              journey_run_id: 701,
              analysis_run_id: 55,
              status: "failed",
              total_scene_count: 14,
              completed_scene_count: 3,
              remaining_scene_count: 11,
              phase_count: 0,
              has_chapter_summary: false,
              retryable: true,
              user_error_message: "阅读旅程生成失败（审计）",
            },
          });
        }
        return route.fulfill({
          json: {
            journey_run_id: 701,
            analysis_run_id: 55,
            status: "failed",
            user_error_message: "阅读旅程生成失败（审计）",
            retryable: true,
          },
        });
      }
      const visualization = buildVisualizationFixture();
      if (j === "empty") {
        const emptySeries = Object.fromEntries(
          Object.keys(visualization.curve_series || {}).map((key) => [key, []]),
        );
        return route.fulfill({
          json: {
            journey_run_id: 701,
            analysis_run_id: 55,
            status: "succeeded",
            visualization: {
              ...visualization,
              scene_nodes: [],
              phases: [],
              curve_series: emptySeries,
              chapter_summary: {
                ...visualization.chapter_summary,
                chapter_title: "空旅程",
                scene_count: 0,
              },
            },
          },
        });
      }
      return route.fulfill({
        json: {
          journey_run_id: 701,
          analysis_run_id: 55,
          status: "succeeded",
          formula_version: "1.0",
          phases: [],
          scene_profiles: [],
          one_sentence_diagnosis: visualization.chapter_summary?.diagnosis ?? "审计旅程",
          visualization,
        },
      });
    }

    // Chapter scenes list: plain SceneResponse[] (not boundary-review items wrapper).
    if (/\/chapters\/\d+\/scenes(?:\?|$)/.test(url) && method === "GET") {
      return route.fulfill({ json: scenesPayload() });
    }

    if (url.includes("/scenes") || url.includes("boundaries") || url.includes("boundary")) {
      return route.fulfill({
        json: {
          items: [
            {
              id: 1,
              scene_ordinal: 1,
              start_paragraph_id: "B0001-C0001-P0001",
              end_paragraph_id: "B0001-C0001-P0002",
              status: "pending_review",
              summary: "虚构场景一：潮汐钟房",
            },
            {
              id: 2,
              scene_ordinal: 2,
              start_paragraph_id: "B0001-C0001-P0003",
              end_paragraph_id: "B0001-C0001-P0003",
              status: "confirmed",
              summary: "虚构场景二：星港灯火",
            },
          ],
        },
      });
    }

    // Default OK empty object — avoid hanging UI
    return route.fulfill({ json: {} });
  });
}

export { MASKED_KEY_HINT };
