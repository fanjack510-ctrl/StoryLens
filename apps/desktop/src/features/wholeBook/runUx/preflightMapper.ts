/**
 * Maps Phase 1C preflight HTTP response → WholeBookPreflightPageModel.
 * Does not recompute capability/quota/engine/run_creation_enabled.
 */

import {
  assertPreflightGuard,
  isWholeBookAnalysisMode,
  isWholeBookModuleKey,
  resolveModulesWithDependencies,
} from "../contracts/guards";
import {
  WHOLE_BOOK_ANALYSIS_MODES,
  WHOLE_BOOK_MODULE_KEYS,
  type WholeBookAnalysisMode,
  type WholeBookModuleKey,
} from "../contracts/keys";
import type {
  PreflightStagePlanItemDto,
  WholeBookPreflightPageModel,
} from "../contracts/preflight";
import type { Phase1cPreflightApiResponse, StagePlanPreviewRow } from "./types";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBool(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function asNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseModules(raw: unknown): WholeBookModuleKey[] {
  if (!Array.isArray(raw)) return [];
  const out: WholeBookModuleKey[] = [];
  for (const item of raw) {
    if (typeof item === "string" && isWholeBookModuleKey(item)) out.push(item);
  }
  return out;
}

function parseMode(raw: unknown): WholeBookAnalysisMode {
  if (typeof raw === "string" && isWholeBookAnalysisMode(raw)) return raw;
  return "whole_book_native";
}

export function extractSupportedModes(
  response: Phase1cPreflightApiResponse,
): WholeBookAnalysisMode[] {
  const decision = asRecord(response.capability_decision);
  const fromDecision = decision.supported_modes;
  if (Array.isArray(fromDecision)) {
    const modes = fromDecision.filter(
      (m): m is WholeBookAnalysisMode =>
        typeof m === "string" && isWholeBookAnalysisMode(m),
    );
    if (modes.length > 0) return modes;
  }
  // Backend may omit modes while still advertising both catalog modes via notes —
  // never invent "allowed"; only list known catalog modes for UI disable logic.
  return [...WHOLE_BOOK_ANALYSIS_MODES];
}

export function mapStagePlanRows(
  raw: Array<Record<string, unknown>> | undefined,
  autoFilledStages: Set<string> = new Set(),
): StagePlanPreviewRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((row, index) => {
    const stageKey = asString(row.stage_key, `unknown_${index}`);
    const depsRaw = row.dependencies ?? row.depends_on;
    const dependencies = Array.isArray(depsRaw)
      ? depsRaw.filter((d): d is string => typeof d === "string")
      : undefined;
    const produced = Array.isArray(row.produced_module_keys)
      ? row.produced_module_keys.filter((m): m is string => typeof m === "string")
      : [];
    const item: StagePlanPreviewRow = {
      stage_key: stageKey,
      display_name: asString(row.display_name, stageKey),
      order: asNumber(row.order, (index + 1) * 10),
      required: asBool(row.required, true),
      estimated_cost_class: asString(row.estimated_cost_class, "unknown"),
      produced_module_keys: produced,
      resumable: typeof row.resumable === "boolean" ? row.resumable : undefined,
      retryable: typeof row.retryable === "boolean" ? row.retryable : undefined,
      dependencies,
      auto_filled: autoFilledStages.has(stageKey),
      description:
        typeof row.description === "string" ? row.description : undefined,
    };
    return item;
  });
}

function toContractStagePlan(rows: StagePlanPreviewRow[]): PreflightStagePlanItemDto[] {
  return rows.map((row) => ({
    stage_key: row.stage_key,
    display_name: row.display_name,
    order: row.order,
    required: row.required,
    estimated_cost_class: row.estimated_cost_class,
    produced_module_keys: row.produced_module_keys,
  }));
}

/**
 * Fail-closed deny model used when transport fails.
 * Never sets run_creation_enabled / capability.allowed to true.
 */
export function failClosedPreflightModel(
  bookId: number,
  message: string,
  reasonCode = "CAPABILITY_OFFLINE_NOT_ALLOWED",
): WholeBookPreflightPageModel {
  const model: WholeBookPreflightPageModel = {
    book: {
      book_id: bookId,
      title: "（无法加载）",
      chapter_count: 0,
      paragraph_count: 0,
      character_count: 0,
      current_snapshot_id: null,
      snapshot_created_at: null,
      body_changed_since_snapshot: false,
      snapshot_rebuild_required: true,
    },
    snapshot: {
      snapshot_id: null,
      status: null,
      created_at: null,
      chapter_count: 0,
      paragraph_count: 0,
      character_count: 0,
      integrity_ok: false,
    },
    capability: {
      capability_key: "whole_book_analysis",
      allowed: false,
      reason_code: reasonCode,
      availability: "unavailable",
      message,
    },
    quota: {
      allowed: false,
      reason_code: reasonCode,
      remaining: {},
      estimated_usage: {},
    },
    engine: {
      engine_id: null,
      available: false,
      supports_mode: false,
      message: message,
    },
    analysis_mode: "whole_book_native",
    requested_modules: [],
    resolved_modules: [],
    stage_plan: [],
    source_coverage: {
      fulltext_snapshot_ready: false,
      enhanced_asset_coverage_ratio: null,
      scene_coverage_ratio: null,
      reader_journey_coverage_ratio: null,
      chapter_analysis_coverage_ratio: null,
      enhanced_degraded: false,
    },
    estimated_usage: {
      estimated_token_input: null,
      estimated_token_output: null,
      estimated_cost: null,
      estimated_duration_class: "unknown",
      currency: "USD",
    },
    blocking_reasons: [reasonCode, "PREFLIGHT_TRANSPORT_FAILED"],
    warnings: [message],
    run_creation_enabled: false,
    confirmation_required: true,
    auto_fill_notes: [],
    force_start_allowed: false,
  };
  assertPreflightGuard(model);
  return model;
}

export function mapPhase1cPreflightToPageModel(
  response: Phase1cPreflightApiResponse,
  requestedModules?: WholeBookModuleKey[],
): {
  model: WholeBookPreflightPageModel;
  stage_plan_rows: StagePlanPreviewRow[];
  supported_modes: WholeBookAnalysisMode[];
} {
  const bookExtra = asRecord(response.book);
  const snapExtra = asRecord(response.snapshot);
  const capabilityRaw = asRecord(response.capability);
  const decisionRaw = asRecord(response.capability_decision);
  const quotaRaw = asRecord(response.quota_decision);
  const engineRaw = asRecord(response.engine_status);
  const coverageRaw = asRecord(response.source_coverage);
  const usageRaw = asRecord(response.estimated_usage);
  const notes = asRecord(response.notes);

  const analysisMode = parseMode(response.analysis_mode);
  const requested =
    requestedModules && requestedModules.length > 0
      ? requestedModules
      : parseModules(response.requested_modules).length > 0
        ? parseModules(response.requested_modules)
        : parseModules(notes.requested_modules);

  const resolvedFromApi = parseModules(response.resolved_modules);
  const resolved =
    resolvedFromApi.length > 0
      ? resolvedFromApi
      : resolveModulesWithDependencies(
          requested.length > 0 ? requested : [...WHOLE_BOOK_MODULE_KEYS],
        ).modules;

  const autoFillNotes =
    Array.isArray(response.auto_fill_notes) && response.auto_fill_notes.length > 0
      ? response.auto_fill_notes.filter((n): n is string => typeof n === "string")
      : resolveModulesWithDependencies(
          requested.length > 0 ? requested : resolved,
        ).notes;

  const directStages = new Set(
    requested.flatMap((m) => {
      // Display-only: which stages are explicitly required by selected modules.
      // Uses shared MODULE_STAGE_DEPENDENCIES via resolveModulesWithDependencies.
      return resolveModulesWithDependencies([m]).stages;
    }),
  );
  const allStages = new Set(
    resolveModulesWithDependencies(
      requested.length > 0 ? requested : resolved,
    ).stages,
  );
  const autoFilledStages = new Set(
    [...allStages].filter((s) => !directStages.has(s) && requested.length > 0),
  );

  const stagePlanRows = mapStagePlanRows(
    response.stage_plan as Array<Record<string, unknown>>,
    autoFilledStages,
  );

  const snapshotMissing =
    response.snapshot_status === "missing" ||
    (response.book_snapshot_id == null &&
      asNullableNumber(bookExtra.current_snapshot_id) == null);

  const blocking = Array.isArray(response.blocking_reasons)
    ? [...response.blocking_reasons]
    : [];
  const warnings = Array.isArray(response.warnings) ? [...response.warnings] : [];
  if (snapshotMissing && !warnings.some((w) => w.includes("快照") || w.includes("snapshot"))) {
    warnings.push("需要建立快照（Preflight 不会自动创建 Snapshot）");
  }

  // Backend is sole authority — never flip to true on the client.
  const runCreationEnabled = false;
  if (response.run_creation_enabled === true) {
    blocking.push("CLIENT_IGNORED_RUN_CREATION_TRUE");
  }

  const model: WholeBookPreflightPageModel = {
    book: {
      book_id: asNumber(response.book_id),
      title: asString(
        bookExtra.title ?? response.title,
        blocking.includes("BOOK_NOT_FOUND") ? "未知书籍" : `Book #${response.book_id}`,
      ),
      chapter_count: asNumber(bookExtra.chapter_count ?? response.chapter_count),
      paragraph_count: asNumber(
        bookExtra.paragraph_count ?? response.paragraph_count,
        0,
      ),
      character_count: asNumber(
        bookExtra.character_count ?? response.character_count,
      ),
      current_snapshot_id: asNullableNumber(
        bookExtra.current_snapshot_id ?? response.book_snapshot_id,
      ),
      snapshot_created_at: asString(
        bookExtra.snapshot_created_at ?? snapExtra.created_at,
        "",
      ) || null,
      body_changed_since_snapshot: asBool(
        bookExtra.body_changed_since_snapshot,
        false,
      ),
      snapshot_rebuild_required: asBool(
        bookExtra.snapshot_rebuild_required,
        snapshotMissing,
      ),
    },
    snapshot: {
      snapshot_id: asNullableNumber(
        snapExtra.snapshot_id ?? response.book_snapshot_id,
      ),
      status: asString(snapExtra.status ?? response.snapshot_status, "") || null,
      created_at: asString(snapExtra.created_at, "") || null,
      chapter_count: asNumber(snapExtra.chapter_count ?? response.chapter_count),
      paragraph_count: asNumber(snapExtra.paragraph_count, 0),
      character_count: asNumber(
        snapExtra.character_count ?? response.character_count,
      ),
      integrity_ok: asBool(snapExtra.integrity_ok, !snapshotMissing),
    },
    capability: {
      capability_key: asString(
        capabilityRaw.capability_key ?? decisionRaw.capability_key,
        "whole_book_analysis",
      ),
      // Pass-through only — never recompute allowed on the client.
      allowed: asBool(
        capabilityRaw.allowed ?? decisionRaw.allowed,
        false,
      ),
      reason_code: asString(
        capabilityRaw.reason_code ?? decisionRaw.reason_code,
        "CAPABILITY_UNKNOWN",
      ),
      availability: asString(
        capabilityRaw.availability ?? decisionRaw.availability,
        "unavailable",
      ),
      message: asString(
        capabilityRaw.message ??
          decisionRaw.display_message ??
          decisionRaw.message,
        "能力状态由后端决定",
      ),
    },
    quota: {
      // Pass-through only — never recompute quota on the client.
      allowed: asBool(quotaRaw.allowed, false),
      reason_code: asString(quotaRaw.reason_code ?? quotaRaw.reasonCode, ""),
      remaining: asRecord(quotaRaw.remaining),
      estimated_usage: asRecord(quotaRaw.estimated_usage),
    },
    engine: {
      engine_id:
        (typeof response.engine_id === "string" ? response.engine_id : null) ??
        (typeof engineRaw.production_default_engine_id === "string"
          ? engineRaw.production_default_engine_id
          : null),
      // Pass-through production_engine_available — never invent availability.
      available: asBool(engineRaw.production_engine_available, false),
      supports_mode: asBool(
        engineRaw.supports_mode,
        !blocking.includes("CAPABILITY_MODE_NOT_SUPPORTED"),
      ),
      message: asString(
        engineRaw.note ?? engineRaw.message,
        "无生产 Engine；Mock Engine 不可作为生产可用",
      ),
    },
    analysis_mode: analysisMode,
    requested_modules: requested,
    resolved_modules: resolved,
    stage_plan: toContractStagePlan(stagePlanRows),
    source_coverage: {
      fulltext_snapshot_ready: asBool(
        coverageRaw.fulltext_snapshot_ready,
        !snapshotMissing,
      ),
      enhanced_asset_coverage_ratio: asNullableNumber(
        coverageRaw.enhanced_asset_coverage_ratio,
      ),
      scene_coverage_ratio: asNullableNumber(coverageRaw.scene_coverage_ratio),
      reader_journey_coverage_ratio: asNullableNumber(
        coverageRaw.reader_journey_coverage_ratio,
      ),
      chapter_analysis_coverage_ratio: asNullableNumber(
        coverageRaw.chapter_analysis_coverage_ratio,
      ),
      enhanced_degraded: asBool(coverageRaw.enhanced_degraded, false),
    },
    estimated_usage: {
      estimated_token_input: asNullableNumber(usageRaw.estimated_token_input),
      estimated_token_output: asNullableNumber(usageRaw.estimated_token_output),
      estimated_cost: asNullableNumber(usageRaw.estimated_cost),
      estimated_duration_class: asString(
        usageRaw.estimated_duration_class,
        "unknown",
      ),
      currency: asString(usageRaw.currency, "USD"),
    },
    blocking_reasons: blocking,
    warnings,
    run_creation_enabled: runCreationEnabled,
    confirmation_required: asBool(response.confirmation_required, true),
    auto_fill_notes: autoFillNotes,
    force_start_allowed: false,
  };

  assertPreflightGuard(model);
  if (model.run_creation_enabled) {
    throw new Error("run_creation_enabled must remain false in Phase 1D");
  }

  return {
    model,
    stage_plan_rows: stagePlanRows,
    supported_modes: extractSupportedModes(response),
  };
}
