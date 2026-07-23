import { describe, expect, it } from "vitest";
import {
  PATTERN_MAP_SCHEMA_VERSION,
  type PatternMapNodeDto,
} from "./patternMap.draft";
import { validateNarrativePatternMapDto } from "./patternMap.guards";

function sampleNode(overrides: Partial<PatternMapNodeDto> = {}): PatternMapNodeDto {
  return {
    id: "n1",
    parentId: null,
    title: "Root",
    summary: "s",
    nodeType: "book_root",
    depth: 0,
    orderIndex: 0,
    importance: 1,
    confidence: 1,
    startChapterId: 1,
    endChapterId: 10,
    relatedCharacterIds: [],
    relatedStorylineIds: [],
    relatedAssetIds: [],
    evidenceCount: 0,
    childCount: 0,
    collapsedByDefault: false,
    userStatus: "unreviewed",
    ...overrides,
  };
}

describe("patternMap draft DTO", () => {
  it("exports frozen schema version", () => {
    expect(PATTERN_MAP_SCHEMA_VERSION).toBe("pattern-map-draft-1");
  });

  it("accepts a minimal valid map payload", () => {
    const result = validateNarrativePatternMapDto({
      schemaVersion: PATTERN_MAP_SCHEMA_VERSION,
      bookId: 1,
      bookSnapshotId: "snap",
      title: "t",
      generatedAt: "2026-07-23T00:00:00Z",
      defaultFilter: {
        mode: "all",
        storylineIds: [],
        characterIds: [],
        stageIds: [],
        minConfidence: 0,
        includeDisputed: true,
        searchQuery: "",
      },
      defaultViewport: {
        scale: 1,
        translateX: 0,
        translateY: 0,
        focusedNodeId: null,
        selectedNodeId: null,
      },
      nodes: [sampleNode()],
      edges: [],
    });
    expect(result.ok).toBe(true);
  });

  it("rejects invalid nodeType and missing evidence fields", () => {
    const badNode = { ...sampleNode(), nodeType: "chapter" };
    const result = validateNarrativePatternMapDto({
      schemaVersion: PATTERN_MAP_SCHEMA_VERSION,
      bookId: 1,
      bookSnapshotId: "snap",
      title: "t",
      generatedAt: "2026-07-23T00:00:00Z",
      defaultFilter: {
        mode: "all",
        storylineIds: [],
        characterIds: [],
        stageIds: [],
        minConfidence: 0,
        includeDisputed: true,
        searchQuery: "",
      },
      defaultViewport: {
        scale: 1,
        translateX: 0,
        translateY: 0,
        focusedNodeId: null,
        selectedNodeId: null,
      },
      nodes: [badNode],
      edges: [],
      evidenceByNodeId: {
        n1: [{ bookSnapshotId: "snap", chapterId: 1 }],
      },
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.issues.some((i) => i.path.startsWith("nodes"))).toBe(true);
      expect(result.issues.some((i) => i.path.includes("evidenceByNodeId"))).toBe(true);
    }
  });
});
