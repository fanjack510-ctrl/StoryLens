import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../../services/apiClient";
import {
  RUN_CREATE_ENABLED_IN_CLIENT,
  WHOLE_BOOK_PREFLIGHT_PATH,
  WHOLE_BOOK_RUN_CREATE_PATH,
  wholeBookPreflightClient,
  PreflightClientError,
} from "../preflightClient";
import { mapPhase1cPreflightToPageModel } from "../preflightMapper";
import {
  FIXTURE_PHASE1C_BOOK_NOT_FOUND,
  FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
  FIXTURE_PHASE1C_SNAPSHOT_MISSING,
} from "../fixtures/preflightFixtures";
import { assertPreflightGuard } from "../../contracts/guards";

vi.mock("../../../../services/apiClient", async () => {
  const actual = await vi.importActual<
    typeof import("../../../../services/apiClient")
  >("../../../../services/apiClient");
  return {
    ...actual,
    api: vi.fn(),
  };
});

import { api } from "../../../../services/apiClient";

describe("wholeBookPreflightClient", () => {
  beforeEach(() => {
    vi.mocked(api).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads preflight successfully and keeps run_creation_enabled=false", async () => {
    vi.mocked(api).mockResolvedValue(FIXTURE_PHASE1C_PREFLIGHT_RESPONSE);
    const result = await wholeBookPreflightClient.fetch(1, {
      analysis_mode: "whole_book_native",
      requested_modules: ["book_overview"],
    });
    expect(api).toHaveBeenCalledWith(
      "/api/v1/books/1/whole-book-runs/preflight",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.model.run_creation_enabled).toBe(false);
    expect(result.model.force_start_allowed).toBe(false);
    assertPreflightGuard(result.model);
    expect(RUN_CREATE_ENABLED_IN_CLIENT).toBe(false);
    expect(WHOLE_BOOK_PREFLIGHT_PATH).toContain("preflight");
    expect(WHOLE_BOOK_RUN_CREATE_PATH).not.toContain("preflight");
  });

  it("fail-closes on network failure and never allows create", async () => {
    vi.mocked(api).mockRejectedValue(
      new ApiError("BACKEND_OFFLINE", "无法连接", 0),
    );
    await expect(
      wholeBookPreflightClient.fetch(1, {
        analysis_mode: "whole_book_native",
      }),
    ).rejects.toBeInstanceOf(PreflightClientError);

    try {
      await wholeBookPreflightClient.fetch(1, {
        analysis_mode: "whole_book_native",
      });
    } catch (err) {
      const closed = wholeBookPreflightClient.failClosed(
        1,
        err as PreflightClientError,
      );
      expect(closed.run_creation_enabled).toBe(false);
      expect(closed.capability.allowed).toBe(false);
      expect(closed.blocking_reasons.length).toBeGreaterThan(0);
    }
  });

  it("fail-closes offline and does not default allow", async () => {
    vi.mocked(api).mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(
      wholeBookPreflightClient.fetch(2, {
        analysis_mode: "whole_book_enhanced",
      }),
    ).rejects.toMatchObject({ code: "OFFLINE" });
  });

  it("surfaces unknown book blocking reason", () => {
    const mapped = mapPhase1cPreflightToPageModel(FIXTURE_PHASE1C_BOOK_NOT_FOUND);
    expect(mapped.model.blocking_reasons).toContain("BOOK_NOT_FOUND");
    expect(mapped.model.book.title).toContain("未知");
    expect(mapped.model.run_creation_enabled).toBe(false);
  });

  it("shows snapshot required without auto-create", () => {
    const mapped = mapPhase1cPreflightToPageModel(
      FIXTURE_PHASE1C_SNAPSHOT_MISSING,
    );
    expect(
      mapped.model.warnings.some(
        (w) => w.includes("快照") || w.toLowerCase().includes("snapshot"),
      ),
    ).toBe(true);
    expect(mapped.model.book.snapshot_rebuild_required).toBe(true);
    expect(mapped.model.run_creation_enabled).toBe(false);
  });

  it("forces run_creation_enabled false even if payload claims true", () => {
    const mapped = mapPhase1cPreflightToPageModel({
      ...FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
      run_creation_enabled: true,
    });
    expect(mapped.model.run_creation_enabled).toBe(false);
    expect(mapped.model.blocking_reasons).toContain(
      "CLIENT_IGNORED_RUN_CREATION_TRUE",
    );
  });

  it("never calls create-run path from this module", () => {
    expect(WHOLE_BOOK_RUN_CREATE_PATH).toBe(
      "/api/v1/books/{book_id}/whole-book-runs",
    );
    expect(api).not.toHaveBeenCalledWith(
      expect.stringMatching(/whole-book-runs$/),
      expect.anything(),
    );
  });
});
