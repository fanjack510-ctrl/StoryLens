/**
 * mockWholeBookRunClient — Phase 2A Lab HTTP client.
 *
 * ONLY calls /api/v1/labs/whole-book-runs/*
 * NEVER calls formal POST /api/v1/books/{book_id}/whole-book-runs
 * Does not invent Run status or allowed_actions.
 */

import { api, ApiError } from "../../../../services/apiClient";
import {
  MOCK_LAB_REQUEST_MARKER_HEADER,
  MOCK_LAB_REQUEST_MARKER_VALUE,
} from "../contracts/mockLab";
import type { CreateMockWholeBookRunRequest } from "../contracts/createRun";
import type { MockRunActionResult } from "../contracts/actions";
import {
  assertActionResult,
  assertCreateResult,
  assertRunView,
  assertStagesResponse,
} from "./dtoGuards";
import { toMockRunClientError } from "./errors";
import {
  FORMAL_RUN_CREATE_PATH,
  LAB_API_BASE,
  MockRunClientError,
  type MockRunActionBody,
  type MockWholeBookRunViewDto,
  type MockWholeBookStagesResponse,
} from "./types";
import { messageForMockRunError } from "./errors";

export type MockWholeBookRunClientDeps = {
  request?: typeof api;
  /** Test hook: record every path called. */
  onRequestPath?: (method: string, path: string) => void;
};

function labMarkerHeaders(): Record<string, string> {
  return {
    [MOCK_LAB_REQUEST_MARKER_HEADER]: MOCK_LAB_REQUEST_MARKER_VALUE,
  };
}

function mapTransportError(error: unknown): never {
  if (error instanceof ApiError && isMockRunErrorCodeFromApi(error.code)) {
    throw new MockRunClientError(
      error.message || messageForMockRunError(error.code as never),
      error.code as never,
      error.status,
      error,
      Boolean(error.retryable),
    );
  }
  throw toMockRunClientError(error);
}

function isMockRunErrorCodeFromApi(code: string): boolean {
  return code.startsWith("MOCK_");
}

function assertNotFormalCreate(path: string): void {
  if (
    path.includes("/whole-book-runs") &&
    !path.includes("/labs/") &&
    !path.includes("/preflight") &&
    !path.includes("/results")
  ) {
    // Formal create pattern: /api/v1/books/{id}/whole-book-runs
    if (/\/books\/\d+\/whole-book-runs\/?$/.test(path)) {
      throw new MockRunClientError(
        "Formal whole-book run create is forbidden in Mock Lab client",
        "UNKNOWN",
      );
    }
  }
}

export function createMockWholeBookRunClient(deps: MockWholeBookRunClientDeps = {}) {
  const request = deps.request ?? api;
  const calledPaths: Array<{ method: string; path: string }> = [];

  async function labRequest<T>(
    method: string,
    path: string,
    init?: RequestInit & { withMarker?: boolean },
  ): Promise<T> {
    assertNotFormalCreate(path);
    const withMarker = init?.withMarker !== false;
    const headers: Record<string, string> = {
      ...(withMarker ? labMarkerHeaders() : {}),
      ...((init?.headers as Record<string, string>) ?? {}),
    };
    const fullPath = path.startsWith("/") ? path : `${LAB_API_BASE}/${path}`;
    calledPaths.push({ method, path: fullPath });
    deps.onRequestPath?.(method, fullPath);
    try {
      return await request<T>(fullPath, {
        ...init,
        method,
        headers,
      });
    } catch (error) {
      mapTransportError(error);
    }
  }

  return {
    /** Paths recorded for tests (formal create must never appear). */
    getCalledPaths: () => [...calledPaths],
    clearCalledPaths: () => {
      calledPaths.length = 0;
    },
    formalCreatePath: FORMAL_RUN_CREATE_PATH,
    labBase: LAB_API_BASE,

    async create(body: CreateMockWholeBookRunRequest) {
      if (!body.idempotency_key?.trim()) {
        throw new MockRunClientError("idempotency_key required", "DTO_INVALID");
      }
      // Never send full novel body.
      const payload = {
        book_id: body.book_id,
        book_snapshot_id: body.book_snapshot_id,
        analysis_mode: body.analysis_mode,
        requested_modules: [...body.requested_modules],
        configuration_fingerprint: body.configuration_fingerprint,
        idempotency_key: body.idempotency_key,
        mock_profile: body.mock_profile,
        requested_by: body.requested_by,
        preflight_fingerprint: body.preflight_fingerprint,
      };
      const raw = await labRequest<unknown>("POST", LAB_API_BASE, {
        body: JSON.stringify(payload),
        withMarker: true,
      });
      return assertCreateResult(raw);
    },

    async get(runId: number): Promise<MockWholeBookRunViewDto> {
      if (!Number.isFinite(runId) || runId <= 0) {
        throw new MockRunClientError(
          messageForMockRunError("MOCK_RUN_NOT_FOUND"),
          "MOCK_RUN_NOT_FOUND",
          404,
        );
      }
      try {
        const raw = await labRequest<unknown>(
          "GET",
          `${LAB_API_BASE}/${runId}`,
        );
        return assertRunView(raw);
      } catch (error) {
        if (error instanceof MockRunClientError && error.code === "UNKNOWN") {
          // 404 → not found
          if (error.status === 404) {
            throw new MockRunClientError(
              messageForMockRunError("MOCK_RUN_NOT_FOUND"),
              "MOCK_RUN_NOT_FOUND",
              404,
              error,
            );
          }
        }
        throw error;
      }
    },

    async getStages(runId: number): Promise<MockWholeBookStagesResponse> {
      if (!Number.isFinite(runId) || runId <= 0) {
        throw new MockRunClientError(
          messageForMockRunError("MOCK_RUN_NOT_FOUND"),
          "MOCK_RUN_NOT_FOUND",
          404,
        );
      }
      const raw = await labRequest<unknown>(
        "GET",
        `${LAB_API_BASE}/${runId}/stages`,
      );
      return assertStagesResponse(raw);
    },

    async pause(
      runId: number,
      body: MockRunActionBody,
    ): Promise<MockRunActionResult> {
      const raw = await labRequest<unknown>(
        "POST",
        `${LAB_API_BASE}/${runId}/pause`,
        {
          body: JSON.stringify({
            operation_idempotency_key: body.operation_idempotency_key,
            expected_state: body.expected_state ?? null,
            expected_version: body.expected_version ?? null,
          }),
          withMarker: true,
        },
      );
      return assertActionResult(raw);
    },

    async resume(
      runId: number,
      body: MockRunActionBody,
    ): Promise<MockRunActionResult> {
      const raw = await labRequest<unknown>(
        "POST",
        `${LAB_API_BASE}/${runId}/resume`,
        {
          body: JSON.stringify({
            operation_idempotency_key: body.operation_idempotency_key,
            expected_state: body.expected_state ?? null,
            expected_version: body.expected_version ?? null,
          }),
          withMarker: true,
        },
      );
      return assertActionResult(raw);
    },

    async cancel(
      runId: number,
      body: MockRunActionBody & { confirm_cancel: true },
    ): Promise<MockRunActionResult> {
      if (!body.confirm_cancel) {
        throw new MockRunClientError(
          "cancel requires confirm_cancel",
          "MOCK_RUN_OPERATION_NOT_ALLOWED",
        );
      }
      const raw = await labRequest<unknown>(
        "POST",
        `${LAB_API_BASE}/${runId}/cancel`,
        {
          body: JSON.stringify({
            operation_idempotency_key: body.operation_idempotency_key,
            expected_state: body.expected_state ?? null,
            expected_version: body.expected_version ?? null,
            confirm_cancel: true,
          }),
          withMarker: true,
        },
      );
      return assertActionResult(raw);
    },

    async retryStage(
      runId: number,
      stageKey: string,
      body: MockRunActionBody,
    ): Promise<MockRunActionResult> {
      if (!stageKey.trim()) {
        throw new MockRunClientError(
          "retry requires a concrete failed stage_key",
          "MOCK_RUN_OPERATION_NOT_ALLOWED",
        );
      }
      const raw = await labRequest<unknown>(
        "POST",
        `${LAB_API_BASE}/${runId}/stages/${encodeURIComponent(stageKey)}/retry`,
        {
          body: JSON.stringify({
            operation_idempotency_key: body.operation_idempotency_key,
            expected_state: body.expected_state ?? null,
            expected_version: body.expected_version ?? null,
            stage_key: stageKey,
          }),
          withMarker: true,
        },
      );
      return assertActionResult(raw);
    },
  };
}

export type MockWholeBookRunClient = ReturnType<typeof createMockWholeBookRunClient>;

export const mockWholeBookRunClient = createMockWholeBookRunClient();
