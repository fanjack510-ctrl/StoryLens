import { describe, expect, it } from "vitest";
import { validateNarrativePatternMapDto } from "../contracts/patternMap.guards";
import { loadPatternMapMock } from "./loadPatternMapMock";
import { summarizeMapScale } from "../lib/patternMapTree";

describe("pattern-map.mock.json schema", () => {
  it("validates against draft DTO guards", () => {
    const map = loadPatternMapMock();
    const again = validateNarrativePatternMapDto(map);
    expect(again.ok).toBe(true);
  });

  it("has 3–4 layers and ~30–40 default-visible main nodes", () => {
    const map = loadPatternMapMock();
    const scale = summarizeMapScale(map);
    expect(scale.maxDepth).toBeGreaterThanOrEqual(3);
    expect(scale.maxDepth).toBeLessThanOrEqual(4);
    expect(scale.defaultVisibleCount).toBeGreaterThanOrEqual(30);
    expect(scale.defaultVisibleCount).toBeLessThanOrEqual(40);
    expect(scale.fullyExpandedCount).toBeGreaterThanOrEqual(70);
    expect(scale.nodeCount).toBe(scale.fullyExpandedCount);
  });

  it("includes structure stages, storylines, character arcs, evidence, collapse, confidence, userStatus", () => {
    const map = loadPatternMapMock();
    const types = new Set(map.nodes.map((n) => n.nodeType));
    expect(types.has("structure_stage")).toBe(true);
    expect(types.has("storyline")).toBe(true);
    expect(types.has("character_arc")).toBe(true);
    expect(map.nodes.some((n) => n.collapsedByDefault)).toBe(true);
    expect(map.nodes.some((n) => n.confidence > 0 && n.confidence < 1)).toBe(true);
    expect(map.nodes.some((n) => n.userStatus === "confirmed")).toBe(true);
    expect(map.nodes.some((n) => n.userStatus === "disputed")).toBe(true);
    expect(Object.keys(map.evidenceByNodeId ?? {}).length).toBeGreaterThan(0);
    const sample = Object.values(map.evidenceByNodeId ?? {})[0]![0]!;
    expect(sample.paragraphContentHash).toMatch(/^[a-f0-9]{64}$/);
  });

  it("does not use one-node-per-chapter assumption", () => {
    const map = loadPatternMapMock();
    const chapterSpan = Math.max(
      ...map.nodes.map((n) => (n.endChapterId ?? 0) - (n.startChapterId ?? 0) + 1),
    );
    expect(map.nodes.length).toBeLessThan(chapterSpan);
    expect(map.nodes.some((n) => (n.endChapterId ?? 0) - (n.startChapterId ?? 0) > 5)).toBe(
      true,
    );
  });
});
