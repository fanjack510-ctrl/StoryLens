import {
  PATTERN_MAP_NODE_TYPES,
  PATTERN_MAP_SCHEMA_VERSION,
  PATTERN_MAP_USER_STATUSES,
  type NarrativePatternMapDto,
  type PatternMapEdgeDto,
  type PatternMapEvidenceRefDto,
  type PatternMapFilterDto,
  type PatternMapNodeDto,
  type PatternMapNodeType,
  type PatternMapUserStatus,
  type PatternMapViewportDto,
} from "./patternMap.draft";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNodeType(value: unknown): value is PatternMapNodeType {
  return typeof value === "string" && (PATTERN_MAP_NODE_TYPES as readonly string[]).includes(value);
}

function isUserStatus(value: unknown): value is PatternMapUserStatus {
  return (
    typeof value === "string" && (PATTERN_MAP_USER_STATUSES as readonly string[]).includes(value)
  );
}

export function isPatternMapEvidenceRefDto(value: unknown): value is PatternMapEvidenceRefDto {
  if (!isRecord(value)) return false;
  return (
    typeof value.bookSnapshotId === "string" &&
    typeof value.chapterId === "number" &&
    (value.sceneId === null || typeof value.sceneId === "number") &&
    typeof value.paragraphId === "string" &&
    typeof value.paragraphContentHash === "string" &&
    typeof value.label === "string"
  );
}

export function isPatternMapNodeDto(value: unknown): value is PatternMapNodeDto {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    (value.parentId === null || typeof value.parentId === "string") &&
    typeof value.title === "string" &&
    typeof value.summary === "string" &&
    isNodeType(value.nodeType) &&
    typeof value.depth === "number" &&
    typeof value.orderIndex === "number" &&
    typeof value.importance === "number" &&
    typeof value.confidence === "number" &&
    (value.startChapterId === null || typeof value.startChapterId === "number") &&
    (value.endChapterId === null || typeof value.endChapterId === "number") &&
    isStringArray(value.relatedCharacterIds) &&
    isStringArray(value.relatedStorylineIds) &&
    isStringArray(value.relatedAssetIds) &&
    typeof value.evidenceCount === "number" &&
    typeof value.childCount === "number" &&
    typeof value.collapsedByDefault === "boolean" &&
    isUserStatus(value.userStatus)
  );
}

export function isPatternMapEdgeDto(value: unknown): value is PatternMapEdgeDto {
  if (!isRecord(value)) return false;
  const relationOk =
    typeof value.relationType === "string" &&
    [
      "parent_child",
      "setup_payoff",
      "parallel",
      "foreshadow",
      "character_growth",
      "storyline_cross",
    ].includes(value.relationType);
  return (
    typeof value.id === "string" &&
    typeof value.sourceNodeId === "string" &&
    typeof value.targetNodeId === "string" &&
    relationOk &&
    typeof value.confidence === "number" &&
    isStringArray(value.relatedAssetIds) &&
    typeof value.evidenceCount === "number" &&
    (value.label === null || typeof value.label === "string")
  );
}

export function isPatternMapFilterDto(value: unknown): value is PatternMapFilterDto {
  if (!isRecord(value)) return false;
  const modeOk =
    value.mode === "structure_stage" ||
    value.mode === "storyline" ||
    value.mode === "character_growth" ||
    value.mode === "all";
  return (
    modeOk &&
    isStringArray(value.storylineIds) &&
    isStringArray(value.characterIds) &&
    isStringArray(value.stageIds) &&
    typeof value.minConfidence === "number" &&
    typeof value.includeDisputed === "boolean" &&
    typeof value.searchQuery === "string"
  );
}

export function isPatternMapViewportDto(value: unknown): value is PatternMapViewportDto {
  if (!isRecord(value)) return false;
  return (
    typeof value.scale === "number" &&
    typeof value.translateX === "number" &&
    typeof value.translateY === "number" &&
    (value.focusedNodeId === null || typeof value.focusedNodeId === "string") &&
    (value.selectedNodeId === null || typeof value.selectedNodeId === "string")
  );
}

export type PatternMapValidationIssue = {
  path: string;
  message: string;
};

export function validateNarrativePatternMapDto(
  value: unknown,
): { ok: true; data: NarrativePatternMapDto } | { ok: false; issues: PatternMapValidationIssue[] } {
  const issues: PatternMapValidationIssue[] = [];
  if (!isRecord(value)) {
    return { ok: false, issues: [{ path: "", message: "root must be an object" }] };
  }
  if (value.schemaVersion !== PATTERN_MAP_SCHEMA_VERSION) {
    issues.push({
      path: "schemaVersion",
      message: `expected ${PATTERN_MAP_SCHEMA_VERSION}`,
    });
  }
  if (typeof value.bookId !== "number") issues.push({ path: "bookId", message: "must be number" });
  if (typeof value.bookSnapshotId !== "string") {
    issues.push({ path: "bookSnapshotId", message: "must be string" });
  }
  if (typeof value.title !== "string") issues.push({ path: "title", message: "must be string" });
  if (typeof value.generatedAt !== "string") {
    issues.push({ path: "generatedAt", message: "must be string" });
  }
  if (!isPatternMapFilterDto(value.defaultFilter)) {
    issues.push({ path: "defaultFilter", message: "invalid filter dto" });
  }
  if (!isPatternMapViewportDto(value.defaultViewport)) {
    issues.push({ path: "defaultViewport", message: "invalid viewport dto" });
  }
  if (!Array.isArray(value.nodes)) {
    issues.push({ path: "nodes", message: "must be array" });
  } else {
    value.nodes.forEach((node, index) => {
      if (!isPatternMapNodeDto(node)) {
        issues.push({ path: `nodes[${index}]`, message: "invalid node dto" });
      }
    });
  }
  if (!Array.isArray(value.edges)) {
    issues.push({ path: "edges", message: "must be array" });
  } else {
    value.edges.forEach((edge, index) => {
      if (!isPatternMapEdgeDto(edge)) {
        issues.push({ path: `edges[${index}]`, message: "invalid edge dto" });
      }
    });
  }
  if (value.evidenceByNodeId !== undefined) {
    if (!isRecord(value.evidenceByNodeId)) {
      issues.push({ path: "evidenceByNodeId", message: "must be object" });
    } else {
      for (const [nodeId, refs] of Object.entries(value.evidenceByNodeId)) {
        if (!Array.isArray(refs)) {
          issues.push({ path: `evidenceByNodeId.${nodeId}`, message: "must be array" });
          continue;
        }
        refs.forEach((ref, index) => {
          if (!isPatternMapEvidenceRefDto(ref)) {
            issues.push({
              path: `evidenceByNodeId.${nodeId}[${index}]`,
              message: "invalid evidence ref",
            });
          }
        });
      }
    }
  }
  if (issues.length) return { ok: false, issues };
  return { ok: true, data: value as NarrativePatternMapDto };
}
