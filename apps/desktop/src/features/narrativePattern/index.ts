/**
 * Narrative Pattern Map — Phase 0B drafts only.
 *
 * DO NOT register these modules in product routers or Pro navigation.
 * DO NOT treat DTOs as database schema.
 */

export type {
  NarrativePatternMapDto,
  PatternMapEdgeDto,
  PatternMapEvidenceRefDto,
  PatternMapFilterDto,
  PatternMapNodeDto,
  PatternMapNodeType,
  PatternMapUserStatus,
  PatternMapViewportDto,
} from "./contracts/patternMap.draft";

export {
  PATTERN_MAP_NODE_TYPES,
  PATTERN_MAP_SCHEMA_VERSION,
  PATTERN_MAP_USER_STATUSES,
} from "./contracts/patternMap.draft";

export { validateNarrativePatternMapDto } from "./contracts/patternMap.guards";
export { loadPatternMapMock } from "./mocks/loadPatternMapMock";
export { PatternMapPrototype } from "./prototype/PatternMapPrototype";
