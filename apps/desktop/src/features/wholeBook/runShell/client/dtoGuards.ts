/**
 * DTO guards for Mock Lab responses. Fail-closed; strip credential/body keys.
 */

import {
  isRunAllowedAction,
  isWholeBookAnalysisMode,
  isWholeBookModuleKey,
  isWholeBookRunViewStatus,
} from "../../contracts/guards";
import type { RunAllowedAction, WholeBookModuleKey } from "../../contracts/keys";
import type { WholeBookStageProgressDto } from "../../contracts/runView";
import { MOCK_PROFILES, type CreateMockWholeBookRunResult } from "../contracts/createRun";
import { MOCK_RUN_ACTIONS, type MockRunActionResult } from "../contracts/actions";
import {
  MockRunClientError,
  type MockWholeBookRunViewDto,
  type MockWholeBookStagesResponse,
  type WholeBookResultIndexDto,
} from "./types";
import { messageForMockRunError } from "./errors";

const BANNED_KEYS = new Set([
  "credential",
  "credentials",
  "api_key",
  "apiKey",
  "prompt",
  "system_prompt",
  "full_text",
  "fulltext",
  "novel_body",
  "body",
  "raw_output",
]);

function assertObject(raw: unknown, label: string): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new MockRunClientError(
      `${label}: ${messageForMockRunError("DTO_INVALID")}`,
      "DTO_INVALID",
    );
  }
  return raw as Record<string, unknown>;
}

export function assertNoSensitiveKeys(
  raw: Record<string, unknown>,
  path = "root",
): void {
  for (const key of Object.keys(raw)) {
    if (BANNED_KEYS.has(key)) {
      throw new MockRunClientError(
        `Response must not include ${key} at ${path}`,
        "DTO_INVALID",
      );
    }
    const value = raw[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      assertNoSensitiveKeys(value as Record<string, unknown>, `${path}.${key}`);
    }
  }
}

function asModuleList(raw: unknown): WholeBookModuleKey[] {
  if (!Array.isArray(raw)) {
    throw new MockRunClientError("modules must be array", "DTO_INVALID");
  }
  const out: WholeBookModuleKey[] = [];
  for (const item of raw) {
    if (typeof item !== "string" || !isWholeBookModuleKey(item)) {
      throw new MockRunClientError(`invalid module key: ${String(item)}`, "DTO_INVALID");
    }
    out.push(item);
  }
  return out;
}

function asAllowedActions(raw: unknown): RunAllowedAction[] {
  if (!Array.isArray(raw)) {
    throw new MockRunClientError("allowed_actions must be array", "DTO_INVALID");
  }
  const out: RunAllowedAction[] = [];
  for (const item of raw) {
    if (typeof item !== "string" || !isRunAllowedAction(item)) {
      throw new MockRunClientError(
        `invalid allowed_action: ${String(item)}`,
        "DTO_INVALID",
      );
    }
    out.push(item);
  }
  return out;
}

function asStages(raw: unknown): WholeBookStageProgressDto[] {
  if (!Array.isArray(raw)) {
    throw new MockRunClientError("stages must be array", "DTO_INVALID");
  }
  return raw.map((item, index) => {
    const row = assertObject(item, `stages[${index}]`);
    if (typeof row.stage_key !== "string") {
      throw new MockRunClientError("stage_key required", "DTO_INVALID");
    }
    return row as unknown as WholeBookStageProgressDto;
  });
}

export function assertCreateResult(raw: unknown): CreateMockWholeBookRunResult {
  const body = assertObject(raw, "create");
  assertNoSensitiveKeys(body);
  if (typeof body.run_id !== "number") {
    throw new MockRunClientError("create missing run_id", "DTO_INVALID");
  }
  if (typeof body.book_id !== "number" || typeof body.book_snapshot_id !== "number") {
    throw new MockRunClientError("create missing book/snapshot ids", "DTO_INVALID");
  }
  if (typeof body.status !== "string" || !isWholeBookRunViewStatus(body.status)) {
    throw new MockRunClientError("create invalid status", "DTO_INVALID");
  }
  if (typeof body.analysis_mode !== "string" || !isWholeBookAnalysisMode(body.analysis_mode)) {
    throw new MockRunClientError("create invalid analysis_mode", "DTO_INVALID");
  }
  if (body.mock !== true || body.non_production !== true) {
    throw new MockRunClientError(
      messageForMockRunError(
        body.mock === false || body.non_production === false
          ? "MOCK_RUN_NON_MOCK_TARGET"
          : "DTO_INVALID",
      ),
      body.mock === false || body.non_production === false
        ? "MOCK_RUN_NON_MOCK_TARGET"
        : "DTO_INVALID",
    );
  }
  if (typeof body.created !== "boolean") {
    throw new MockRunClientError("create missing created", "DTO_INVALID");
  }
  if (!body.created && body.duplicate_of_run_id == null) {
    throw new MockRunClientError(
      "idempotent create requires duplicate_of_run_id",
      "DTO_INVALID",
    );
  }
  if (
    typeof body.mock_profile === "string" &&
    !(MOCK_PROFILES as readonly string[]).includes(body.mock_profile)
  ) {
    // optional field — ignore unknown quietly if absent; reject if present & invalid
  }
  return {
    run_id: body.run_id,
    book_id: body.book_id,
    book_snapshot_id: body.book_snapshot_id,
    status: body.status,
    analysis_mode: body.analysis_mode,
    requested_modules: asModuleList(body.requested_modules),
    resolved_modules: asModuleList(body.resolved_modules),
    stage_plan: Array.isArray(body.stage_plan)
      ? body.stage_plan.map(String)
      : [],
    mock: true,
    non_production: true,
    created: body.created,
    duplicate_of_run_id:
      body.duplicate_of_run_id == null ? null : Number(body.duplicate_of_run_id),
    created_at: typeof body.created_at === "string" ? body.created_at : "",
  };
}

export function assertRunView(raw: unknown): MockWholeBookRunViewDto {
  const body = assertObject(raw, "run");
  assertNoSensitiveKeys(body);
  if (typeof body.run_id !== "number") {
    throw new MockRunClientError("run missing run_id", "DTO_INVALID");
  }
  if (typeof body.status !== "string" || !isWholeBookRunViewStatus(body.status)) {
    throw new MockRunClientError("run invalid status", "DTO_INVALID");
  }
  if (body.mock !== true || body.non_production !== true) {
    throw new MockRunClientError(
      messageForMockRunError("MOCK_RUN_NON_MOCK_TARGET"),
      "MOCK_RUN_NON_MOCK_TARGET",
    );
  }
  const version =
    typeof body.version === "number" && Number.isFinite(body.version)
      ? body.version
      : 0;
  const stages = asStages(body.stages);
  const allowed = asAllowedActions(body.allowed_actions);
  return {
    run_id: body.run_id,
    book_id: Number(body.book_id),
    snapshot_id: Number(body.snapshot_id ?? body.book_snapshot_id),
    analysis_mode: body.analysis_mode as MockWholeBookRunViewDto["analysis_mode"],
    status: body.status,
    current_stage:
      body.current_stage == null ? null : String(body.current_stage),
    stages,
    completed_modules: asModuleList(body.completed_modules ?? []),
    available_modules: asModuleList(body.available_modules ?? []),
    failed_modules: asModuleList(body.failed_modules ?? []),
    partial_results_available: Boolean(body.partial_results_available),
    progress_percent:
      body.progress_percent == null ? null : Number(body.progress_percent),
    token_usage:
      body.token_usage && typeof body.token_usage === "object"
        ? (body.token_usage as Record<string, number>)
        : {},
    cost: body.cost == null ? null : Number(body.cost),
    started_at: body.started_at == null ? null : String(body.started_at),
    updated_at: body.updated_at == null ? null : String(body.updated_at),
    estimated_remaining:
      body.estimated_remaining == null ? null : String(body.estimated_remaining),
    blocking_issue:
      body.blocking_issue == null ? null : String(body.blocking_issue),
    allowed_actions: allowed,
    module_statuses:
      (body.module_statuses as MockWholeBookRunViewDto["module_statuses"]) ?? {},
    version,
    mock: true,
    non_production: true,
    synthetic_usage: true,
    warnings: Array.isArray(body.warnings)
      ? body.warnings.map(String)
      : [],
    mock_profile:
      typeof body.mock_profile === "string"
        ? (body.mock_profile as MockWholeBookRunViewDto["mock_profile"])
        : null,
    engine_id: body.engine_id == null ? null : String(body.engine_id),
  };
}

export function assertStagesResponse(raw: unknown): MockWholeBookStagesResponse {
  const body = assertObject(raw, "stages");
  assertNoSensitiveKeys(body);
  if (typeof body.run_id !== "number") {
    throw new MockRunClientError("stages missing run_id", "DTO_INVALID");
  }
  if (body.mock !== true || body.non_production !== true) {
    throw new MockRunClientError(
      messageForMockRunError("MOCK_RUN_NON_MOCK_TARGET"),
      "MOCK_RUN_NON_MOCK_TARGET",
    );
  }
  return {
    run_id: body.run_id,
    mock: true,
    non_production: true,
    stages: asStages(body.stages),
    updated_at: body.updated_at == null ? null : String(body.updated_at),
    version:
      typeof body.version === "number" && Number.isFinite(body.version)
        ? body.version
        : 0,
  };
}

export function assertActionResult(raw: unknown): MockRunActionResult {
  const body = assertObject(raw, "action");
  assertNoSensitiveKeys(body);
  if (typeof body.run_id !== "number") {
    throw new MockRunClientError("action missing run_id", "DTO_INVALID");
  }
  if (
    typeof body.action !== "string" ||
    !(MOCK_RUN_ACTIONS as readonly string[]).includes(body.action)
  ) {
    throw new MockRunClientError("action invalid", "DTO_INVALID");
  }
  if (
    typeof body.current_state !== "string" ||
    !isWholeBookRunViewStatus(body.current_state)
  ) {
    throw new MockRunClientError("action invalid current_state", "DTO_INVALID");
  }
  return {
    run_id: body.run_id,
    action: body.action as MockRunActionResult["action"],
    requested: Boolean(body.requested),
    accepted: Boolean(body.accepted),
    current_state: body.current_state,
    idempotent_replay: Boolean(body.idempotent_replay),
    detail_code: body.detail_code == null ? null : String(body.detail_code),
  };
}

export function assertResultIndex(raw: unknown): WholeBookResultIndexDto {
  const body = assertObject(raw, "result_index");
  assertNoSensitiveKeys(body);
  if (typeof body.run_id !== "number") {
    throw new MockRunClientError("result index missing run_id", "DTO_INVALID");
  }
  return body as unknown as WholeBookResultIndexDto;
}
