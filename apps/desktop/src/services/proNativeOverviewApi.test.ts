import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./apiClient";
import {
  FIXTURE_CREATE_DEFAULTS,
  proNativeOverviewApi,
  remapOverviewApiError,
  resolveCreateBinding,
} from "./proNativeOverviewApi";
import { firstEvidenceHref, overviewEvidenceHref } from "./proNativeOverviewDeepLink";
import {
  FIXTURE_ENGINE_ID,
  FIXTURE_ENGINE_LABEL,
  FORMAL_ENGINE_LABEL,
  PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
  resolveEnginePresentation,
} from "./proNativeOverviewFlag";
import { buildStageList, fieldStatusLabel } from "./proNativeOverviewStages";

describe("proNativeOverviewApi", () => {
  it("exposes fixture create defaults for walking skeleton", () => {
    expect(FIXTURE_CREATE_DEFAULTS.mode).toBe("whole_book_native");
    expect(FIXTURE_CREATE_DEFAULTS.engine_label).toBe(FIXTURE_ENGINE_LABEL);
  });

  it("resolves fixture vs formal create binding", () => {
    const fixture = resolveCreateBinding({
      book_id: "1",
      chapter_count: 1,
      paragraph_count: 1,
      character_count: 10,
      engine_id: FIXTURE_ENGINE_ID,
    });
    expect(fixture.engine.isFixture).toBe(true);
    expect(fixture.model_id).toBe(FIXTURE_ENGINE_ID);

    const formal = resolveCreateBinding({
      book_id: "1",
      chapter_count: 1,
      paragraph_count: 1,
      character_count: 10,
      engine_id: PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
      provider_id: "aliyun_qwen",
      model_id: "qwen-plus",
    });
    expect(formal.engine.isFixture).toBe(false);
    expect(formal.engine.label).toBe(FORMAL_ENGINE_LABEL);
    expect(formal.provider_id).toBe("aliyun_qwen");
    expect(formal.model_id).toBe("qwen-plus");
  });

  it("remaps nested error envelope codes", () => {
    try {
      remapOverviewApiError(
        new ApiError("HTTP_ERROR", "fail", 403, {
          error: { code: "PRO_LICENSE_REQUIRED", message: "需要 Pro", retryable: false },
        }),
      );
      throw new Error("expected throw");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("PRO_LICENSE_REQUIRED");
      expect((error as ApiError).message).toBe("需要 Pro");
    }
  });

  it("calls contract paths via api client including retry and resume", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo, init?: RequestInit) => {
      const href = String(input);
      if (href.endsWith("/whole-book-runs/preflight")) {
        return new Response(
          JSON.stringify({
            book_id: "1",
            chapter_count: 1,
            paragraph_count: 2,
            character_count: 10,
            license_allowed: true,
            blocking_errors: [],
            estimated_windows: 1,
            estimated_tokens: 100,
            estimated_cost: 0.01,
            engine_id: FIXTURE_ENGINE_ID,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.endsWith("/whole-book-runs") && !href.includes("preflight")) {
        return new Response(
          JSON.stringify({
            run_id: "9",
            book_id: "1",
            snapshot_id: "1",
            status: "pending",
            progress: { completed_windows: 0, total_windows: 1 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.endsWith("/whole-book-runs/9/retry")) {
        expect(init?.method).toBe("POST");
        return new Response(
          JSON.stringify({
            run_id: "9",
            book_id: "1",
            snapshot_id: "1",
            status: "analyzing",
            progress: { completed_windows: 0, total_windows: 1 },
            retryable: false,
            actions: { can_retry: false, can_resume: false },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.endsWith("/whole-book-runs/9/resume")) {
        expect(init?.method).toBe("POST");
        return new Response(
          JSON.stringify({
            run_id: "9",
            book_id: "1",
            snapshot_id: "1",
            status: "analyzing",
            progress: { completed_windows: 1, total_windows: 1 },
            retryable: false,
            actions: { can_retry: false, can_resume: false },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.includes("/whole-book-runs/9/overview")) {
        return new Response(
          JSON.stringify({
            run: { run_id: "9", status: "completed" },
            book: { book_id: "1" },
            snapshot: { snapshot_id: "1" },
            coverage: {
              original_paragraphs_total: 1,
              original_paragraphs_covered: 1,
              original_coverage_percent: 100,
              windows_total: 1,
              windows_completed: 1,
            },
            overview: {},
            evidence_index: [],
            generated_at: "2026-07-25T00:00:00Z",
            engine_version: "walking-skeleton-1",
            prompt_version: "fixture-no-prompt",
            contract_version: "1.0",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.includes("/whole-book-runs/9")) {
        return new Response(
          JSON.stringify({
            run_id: "9",
            book_id: "1",
            snapshot_id: "1",
            status: "analyzing",
            progress: { completed_windows: 0, total_windows: 1 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await proNativeOverviewApi.preflight(1);
    await proNativeOverviewApi.createRun(1, {
      provider_id: "fixture",
      model_id: "fixture-native-overview-v1",
      client_request_id: "req-1",
      consent: {
        estimated_tokens: 1,
        estimated_cost: 0,
        currency: "CNY",
        confirmed: true,
      },
    });
    await proNativeOverviewApi.getRun("9");
    await proNativeOverviewApi.retryRun("9", { client_request_id: "retry-1", reason: "test" });
    await proNativeOverviewApi.resumeRun("9", { client_request_id: "resume-1" });
    await proNativeOverviewApi.getOverview("9");

    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.some((u) => u.includes("/api/v1/books/1/whole-book-runs/preflight"))).toBe(true);
    expect(urls.some((u) => /\/api\/v1\/books\/1\/whole-book-runs$/.test(u))).toBe(true);
    expect(urls.some((u) => u.includes("/api/v1/whole-book-runs/9/overview"))).toBe(true);
    expect(urls.some((u) => /\/api\/v1\/whole-book-runs\/9$/.test(u))).toBe(true);
    expect(urls.some((u) => u.includes("/api/v1/whole-book-runs/9/retry"))).toBe(true);
    expect(urls.some((u) => u.includes("/api/v1/whole-book-runs/9/resume"))).toBe(true);

    vi.unstubAllGlobals();
  });
});

describe("proNativeOverviewDeepLink", () => {
  it("builds reader deep link and resolves evidence refs", () => {
    expect(overviewEvidenceHref(1, { chapter_id: "2", paragraph_id: "p1" })).toBe(
      "/books/1?chapter=2&paragraph=p1&view=reading",
    );
    expect(
      firstEvidenceHref(
        1,
        ["ev-1"],
        [
          {
            evidence_id: "ev-1",
            chapter_id: "2",
            paragraph_id: "p1",
            deep_link: { chapter_id: "2", paragraph_id: "p1" },
          },
        ],
      ),
    ).toBe("/books/1?chapter=2&paragraph=p1&view=reading");
    expect(firstEvidenceHref(1, ["missing"], [])).toBeNull();
  });
});

describe("proNativeOverviewFlag / stages", () => {
  it("labels fixture vs formal engines distinctly", () => {
    expect(resolveEnginePresentation(FIXTURE_ENGINE_ID).label).toBe(FIXTURE_ENGINE_LABEL);
    expect(resolveEnginePresentation(PRIVATE_NATIVE_OVERVIEW_ENGINE_ID).label).toBe(
      FORMAL_ENGINE_LABEL,
    );
  });

  it("builds multi-stage list without inventing percentages", () => {
    const stages = buildStageList("extract_overview_facts", "analyzing");
    expect(stages[0].state).toBe("done");
    expect(stages.find((s) => s.key === "extract_overview_facts")?.state).toBe("current");
    expect(stages.find((s) => s.key === "finalize")?.state).toBe("pending");
  });

  it("maps field statuses for results UI", () => {
    expect(fieldStatusLabel("supported")).toBe("已支持");
    expect(fieldStatusLabel("low_confidence")).toBe("低置信度");
    expect(fieldStatusLabel("insufficient_evidence")).toBe("证据不足");
    expect(fieldStatusLabel("conflicted")).toBe("存在冲突");
  });
});
