import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createMockWholeBookRunClient,
  LAB_API_BASE,
  FORMAL_RUN_CREATE_PATH,
  MockRunClientError,
} from "../client";
import {
  MOCK_LAB_REQUEST_MARKER_HEADER,
  MOCK_LAB_REQUEST_MARKER_VALUE,
} from "../contracts/mockLab";
import {
  MOCK_CREATE_RESULT_DUP,
  MOCK_CREATE_RESULT_NEW,
  MOCK_FIXTURE_RUNNING,
  mockActionResult,
} from "./fixtures";

afterEach(() => {
  vi.restoreAllMocks();
});

const createBody = {
  book_id: 1,
  book_snapshot_id: 11,
  analysis_mode: "whole_book_native" as const,
  requested_modules: ["book_overview" as const],
  configuration_fingerprint: "cfg",
  idempotency_key: "idem-1",
  mock_profile: "deterministic_minimal" as const,
  requested_by: "tester",
  preflight_fingerprint: "pf",
};

describe("mockWholeBookRunClient", () => {
  it("create posts to lab path with marker and never formal create", async () => {
    const paths: string[] = [];
    const request = vi.fn(async (path: string, init?: RequestInit) => {
      paths.push(`${init?.method ?? "GET"} ${path}`);
      const headers = init?.headers as Record<string, string>;
      expect(headers[MOCK_LAB_REQUEST_MARKER_HEADER]).toBe(
        MOCK_LAB_REQUEST_MARKER_VALUE,
      );
      expect(JSON.parse(String(init?.body))).not.toHaveProperty("full_text");
      return MOCK_CREATE_RESULT_NEW;
    });
    const client = createMockWholeBookRunClient({ request: request as never });
    const result = await client.create(createBody);
    expect(result.created).toBe(true);
    expect(result.mock).toBe(true);
    expect(paths[0]).toBe(`POST ${LAB_API_BASE}`);
    expect(paths.join("\n")).not.toContain("/books/");
    expect(client.formalCreatePath).toBe(FORMAL_RUN_CREATE_PATH);
  });

  it("create duplicate returns created=false", async () => {
    const request = vi.fn(async () => MOCK_CREATE_RESULT_DUP);
    const client = createMockWholeBookRunClient({ request: request as never });
    const result = await client.create(createBody);
    expect(result.created).toBe(false);
    expect(result.duplicate_of_run_id).toBe(101);
  });

  it("get returns run view and rejects non-mock target", async () => {
    const request = vi.fn(async () => MOCK_FIXTURE_RUNNING);
    const client = createMockWholeBookRunClient({ request: request as never });
    const view = await client.get(101);
    expect(view.run_id).toBe(101);
    expect(view.mock).toBe(true);
    expect(view.allowed_actions).toContain("pause");

    const bad = createMockWholeBookRunClient({
      request: vi.fn(async () => ({
        ...MOCK_FIXTURE_RUNNING,
        mock: false,
        non_production: false,
      })) as never,
    });
    await expect(bad.get(101)).rejects.toMatchObject({
      code: "MOCK_RUN_NON_MOCK_TARGET",
    });
  });

  it("getStages returns stages", async () => {
    const request = vi.fn(async () => ({
      run_id: 101,
      mock: true,
      non_production: true,
      stages: MOCK_FIXTURE_RUNNING.stages,
      updated_at: "2026-07-23T01:05:00Z",
      version: 3,
    }));
    const client = createMockWholeBookRunClient({ request: request as never });
    const stages = await client.getStages(101);
    expect(stages.stages.length).toBeGreaterThan(0);
    expect(stages.mock).toBe(true);
  });

  it("pause/resume/cancel/retry include lab marker and idempotency", async () => {
    const seen: Array<{ path: string; body: Record<string, unknown> }> = [];
    const request = vi.fn(async (path: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      seen.push({ path, body });
      const headers = init?.headers as Record<string, string>;
      expect(headers[MOCK_LAB_REQUEST_MARKER_HEADER]).toBe("1");
      expect(body.operation_idempotency_key).toBeTruthy();
      if (path.endsWith("/pause")) return mockActionResult("pause", "paused");
      if (path.endsWith("/resume")) return mockActionResult("resume", "running");
      if (path.endsWith("/cancel")) return mockActionResult("cancel", "cancelled");
      return mockActionResult("retry", "running");
    });
    const client = createMockWholeBookRunClient({ request: request as never });
    await client.pause(101, {
      operation_idempotency_key: "op-pause",
      expected_state: "running",
      expected_version: 1,
    });
    await client.resume(101, {
      operation_idempotency_key: "op-resume",
      expected_state: "paused",
      expected_version: 2,
    });
    await client.cancel(101, {
      operation_idempotency_key: "op-cancel",
      expected_state: "running",
      expected_version: 3,
      confirm_cancel: true,
    });
    await client.retryStage(101, "analyze_structure", {
      operation_idempotency_key: "op-retry",
      expected_state: "failed",
      expected_version: 4,
    });
    expect(seen.map((s) => s.path)).toEqual([
      `${LAB_API_BASE}/101/pause`,
      `${LAB_API_BASE}/101/resume`,
      `${LAB_API_BASE}/101/cancel`,
      `${LAB_API_BASE}/101/stages/analyze_structure/retry`,
    ]);
  });

  it("unknown run and network fail-closed", async () => {
    const client404 = createMockWholeBookRunClient({
      request: vi.fn(async () => {
        throw new MockRunClientError("not found", "MOCK_RUN_NOT_FOUND", 404);
      }) as never,
    });
    await expect(client404.get(999)).rejects.toMatchObject({
      code: "MOCK_RUN_NOT_FOUND",
    });

    const clientNet = createMockWholeBookRunClient({
      request: vi.fn(async () => {
        throw new TypeError("network down");
      }) as never,
    });
    await expect(clientNet.get(101)).rejects.toMatchObject({ code: "NETWORK" });
  });

  it("rejects credential/full_text in DTO", async () => {
    const client = createMockWholeBookRunClient({
      request: vi.fn(async () => ({
        ...MOCK_FIXTURE_RUNNING,
        credential: "secret",
      })) as never,
    });
    await expect(client.get(101)).rejects.toMatchObject({ code: "DTO_INVALID" });
  });
});
