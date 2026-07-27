import {
  EVIDENCE_INTEGRITY_STATUSES,
  PRODUCT_MODULE_STAGE_DEPENDENCIES,
  NARRATIVE_REVIEW_ACTIONS,
  RUN_ALLOWED_ACTIONS,
  WHOLE_BOOK_ANALYSIS_MODES,
  WHOLE_BOOK_MODULE_KEYS,
  WHOLE_BOOK_MODULE_STATUSES,
  WHOLE_BOOK_RUN_VIEW_STATUSES,
  type EvidenceIntegrityStatus,
  type NarrativeReviewAction,
  type RunAllowedAction,
  type WholeBookAnalysisMode,
  type WholeBookModuleKey,
  type WholeBookModuleStatus,
  type WholeBookRunViewStatus,
} from "./keys";
import type { NarrativeReviewActionRequest } from "./review";
import type { WholeBookEvidenceRefDto } from "./evidence";
import type { WholeBookPreflightPageModel } from "./preflight";
import type { WholeBookResultEnvelope } from "./resultEnvelope";
import { MAX_PARAGRAPH_PREVIEW_CHARS } from "./evidence";
import {
  PATTERN_DTO_HAS_ORM_TABLE,
  STRUCTURE_MAP_DEFAULT_MAX_EDGES,
  STRUCTURE_MAP_DEFAULT_MAX_NODES,
} from "./structureMap";

export function isWholeBookModuleKey(value: string): value is WholeBookModuleKey {
  return (WHOLE_BOOK_MODULE_KEYS as readonly string[]).includes(value);
}

export function isWholeBookAnalysisMode(
  value: string,
): value is WholeBookAnalysisMode {
  return (WHOLE_BOOK_ANALYSIS_MODES as readonly string[]).includes(value);
}

export function isWholeBookRunViewStatus(
  value: string,
): value is WholeBookRunViewStatus {
  return (WHOLE_BOOK_RUN_VIEW_STATUSES as readonly string[]).includes(value);
}

export function isWholeBookModuleStatus(
  value: string,
): value is WholeBookModuleStatus {
  return (WHOLE_BOOK_MODULE_STATUSES as readonly string[]).includes(value);
}

export function isRunAllowedAction(value: string): value is RunAllowedAction {
  return (RUN_ALLOWED_ACTIONS as readonly string[]).includes(value);
}

export function isEvidenceIntegrityStatus(
  value: string,
): value is EvidenceIntegrityStatus {
  return (EVIDENCE_INTEGRITY_STATUSES as readonly string[]).includes(value);
}

export function isNarrativeReviewAction(
  value: string,
): value is NarrativeReviewAction {
  return (NARRATIVE_REVIEW_ACTIONS as readonly string[]).includes(value);
}

export function resolveModulesWithDependencies(
  requested: WholeBookModuleKey[],
): { modules: WholeBookModuleKey[]; stages: string[]; notes: string[] } {
  const modules =
    requested.length === 0
      ? [...WHOLE_BOOK_MODULE_KEYS]
      : [...new Set(requested)];
  const stages: string[] = [];
  const notes: string[] = [];
  for (const module of modules) {
    const deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[module];
    notes.push(`module ${module} requires stages: ${deps.join(", ")}`);
    for (const stage of deps) {
      if (!stages.includes(stage)) stages.push(stage);
    }
  }
  return { modules, stages, notes };
}

export function assertPreflightGuard(model: WholeBookPreflightPageModel): void {
  if (model.force_start_allowed !== false) {
    throw new Error("force_start_allowed must be false");
  }
  const expected =
    model.backend_run_creation_enabled && model.client_run_creation_enabled;
  if (model.effective_run_creation_enabled !== expected) {
    throw new Error(
      "effective_run_creation_enabled must equal backend AND client flags",
    );
  }
  if (model.run_creation_enabled !== model.effective_run_creation_enabled) {
    throw new Error(
      "run_creation_enabled must equal effective_run_creation_enabled",
    );
  }
  if (model.effective_run_creation_enabled && model.blocking_reasons.length > 0) {
    throw new Error(
      "effective_run_creation_enabled cannot be true with blocking_reasons",
    );
  }
}

export function assertEvidencePreview(dto: WholeBookEvidenceRefDto): void {
  if (dto.paragraph_preview.length > MAX_PARAGRAPH_PREVIEW_CHARS) {
    throw new Error("paragraph_preview too long");
  }
}

export function assertReviewAction(req: NarrativeReviewActionRequest): void {
  if (req.expected_version === "" || req.expected_version == null) {
    throw new Error("expected_version required");
  }
  if ("is_canonical" in (req.correction_payload ?? {})) {
    throw new Error("frontend must not set is_canonical");
  }
  if (req.action === "correct" && Object.keys(req.correction_payload).length === 0) {
    throw new Error("correct requires correction_payload");
  }
  if (req.action === "resolve_conflict") {
    if (!("schema" in req.resolution_payload) || !("version" in req.resolution_payload)) {
      throw new Error("resolve_conflict requires schema/version");
    }
  }
}

export function assertResultEnvelope(env: WholeBookResultEnvelope): void {
  if (!env.schema || !env.version) {
    throw new Error("schema/version required");
  }
  if ("full_text" in env.payload || "body" in env.payload) {
    throw new Error("payload must not embed full body");
  }
}

export function assertStructureMapLimits(nodeCount: number, edgeCount: number): void {
  if (nodeCount > STRUCTURE_MAP_DEFAULT_MAX_NODES) {
    throw new Error("too many nodes");
  }
  if (edgeCount > STRUCTURE_MAP_DEFAULT_MAX_EDGES) {
    throw new Error("too many edges");
  }
}

export function assertPatternDtoNotOrm(): void {
  if (PATTERN_DTO_HAS_ORM_TABLE) {
    throw new Error("Pattern DTO must not map to ORM table");
  }
}
