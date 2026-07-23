/**
 * Read-only whole-book Preflight client adapter.
 * POST /api/v1/books/{book_id}/whole-book-runs/preflight
 *
 * Never calls POST /whole-book-runs. Never recomputes allow flags.
 */

import { api, ApiError } from "../../../services/apiClient";
import { assertPreflightGuard } from "../contracts/guards";
import type { WholeBookPreflightPageModel } from "../contracts/preflight";
import {
  failClosedPreflightModel,
  mapPhase1cPreflightToPageModel,
} from "./preflightMapper";
import type {
  Phase1cPreflightApiResponse,
  PreflightLoadError,
  StagePlanPreviewRow,
  WholeBookPreflightRequest,
} from "./types";
import type { WholeBookAnalysisMode } from "../contracts/keys";

export class PreflightClientError extends Error {
  constructor(
    message: string,
    public readonly code: PreflightLoadError["code"],
    public readonly cause?: unknown,
  ) {
    super(message);
    this.name = "PreflightClientError";
  }

  toLoadError(): PreflightLoadError {
    return { code: this.code, message: this.message };
  }
}

export type PreflightClientResult = {
  model: WholeBookPreflightPageModel;
  stage_plan_rows: StagePlanPreviewRow[];
  supported_modes: WholeBookAnalysisMode[];
  raw: Phase1cPreflightApiResponse;
};

function toClientError(error: unknown): PreflightClientError {
  if (error instanceof PreflightClientError) return error;
  if (error instanceof ApiError) {
    if (error.code === "BACKEND_OFFLINE" || error.status === 0) {
      return new PreflightClientError(
        "离线状态下无法完成 Preflight 检查，默认不允许启动",
        "OFFLINE",
        error,
      );
    }
    return new PreflightClientError(
      error.message || "Preflight 请求失败",
      "HTTP",
      error,
    );
  }
  if (error instanceof TypeError) {
    return new PreflightClientError(
      "离线状态下无法完成 Preflight 检查，默认不允许启动",
      "OFFLINE",
      error,
    );
  }
  return new PreflightClientError(
    error instanceof Error ? error.message : "Preflight 请求失败",
    "NETWORK",
    error,
  );
}

function assertResponseShape(raw: unknown): Phase1cPreflightApiResponse {
  if (!raw || typeof raw !== "object") {
    throw new PreflightClientError("Preflight 响应无效", "DTO_INVALID");
  }
  const body = raw as Record<string, unknown>;
  if (typeof body.book_id !== "number") {
    throw new PreflightClientError("Preflight 缺少 book_id", "DTO_INVALID");
  }
  if (!Array.isArray(body.blocking_reasons)) {
    throw new PreflightClientError(
      "Preflight 缺少 blocking_reasons",
      "DTO_INVALID",
    );
  }
  return body as Phase1cPreflightApiResponse;
}

export const wholeBookPreflightClient = {
  /**
   * Read-only preflight. Fail-closed on transport errors.
   * Does NOT create AnalysisRun / Snapshot / quota reservation.
   */
  async fetch(
    bookId: number,
    request: WholeBookPreflightRequest,
  ): Promise<PreflightClientResult> {
    if (!Number.isFinite(bookId) || bookId <= 0) {
      throw new PreflightClientError("无效的 book_id", "BOOK_NOT_FOUND");
    }

    try {
      const rawUnknown = await api<unknown>(
        `/api/v1/books/${bookId}/whole-book-runs/preflight`,
        {
          method: "POST",
          body: JSON.stringify({
            analysis_mode: request.analysis_mode,
            requested_modules: request.requested_modules ?? [],
            book_snapshot_id: request.book_snapshot_id ?? null,
            configuration_fingerprint:
              request.configuration_fingerprint ?? null,
          }),
        },
      );
      const raw = assertResponseShape(rawUnknown);
      const mapped = mapPhase1cPreflightToPageModel(
        raw,
        request.requested_modules,
      );
      assertPreflightGuard(mapped.model);
      if (mapped.model.effective_run_creation_enabled !== false) {
        throw new PreflightClientError(
          "effective_run_creation_enabled 必须为 false",
          "DTO_INVALID",
        );
      }
      if (mapped.model.blocking_reasons.includes("BOOK_NOT_FOUND")) {
        // Structured deny — still return model so UI can show explicit error.
        return { ...mapped, raw };
      }
      return { ...mapped, raw };
    } catch (error) {
      if (error instanceof PreflightClientError) throw error;
      throw toClientError(error);
    }
  },

  /** Fail-closed fallback model for UI when fetch throws. */
  failClosed(
    bookId: number,
    error: PreflightClientError | PreflightLoadError,
  ): WholeBookPreflightPageModel {
    const message =
      "message" in error ? error.message : "Preflight 失败，默认不允许启动";
    const code =
      "code" in error && typeof error.code === "string"
        ? error.code
        : "CAPABILITY_UNKNOWN";
    return failClosedPreflightModel(bookId, message, code);
  },
};

export type WholeBookPreflightClient = typeof wholeBookPreflightClient;

export {
  RUN_CREATE_ENABLED_IN_CLIENT,
  WHOLE_BOOK_PREFLIGHT_PATH,
  WHOLE_BOOK_RUN_CREATE_PATH,
} from "./constants";
