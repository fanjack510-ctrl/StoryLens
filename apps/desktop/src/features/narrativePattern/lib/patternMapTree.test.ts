import { describe, expect, it } from "vitest";
import { layoutPatternTree } from "./patternMapLayout";
import {
  collectVisibleNodes,
  expandAll,
  expandAncestorsForNode,
  findMatchingNodeIds,
  initialCollapseState,
  setCollapsed,
} from "./patternMapTree";
import { loadPatternMapMock } from "../mocks/loadPatternMapMock";
import {
  buildEvidenceDeepLinkParams,
  CURRENT_EVIDENCE_LOCATE_CAPABILITY,
  evidenceDeepLinkHref,
} from "./evidenceDeepLink";

describe("patternMapTree", () => {
  it("defaults to ~36–40 visible and expands toward ~80", () => {
    const map = loadPatternMapMock();
    const collapsed = initialCollapseState(map.nodes);
    const defaultVisible = collectVisibleNodes(map.nodes, collapsed);
    const expanded = collectVisibleNodes(map.nodes, expandAll(map.nodes));
    expect(defaultVisible.length).toBeGreaterThanOrEqual(30);
    expect(defaultVisible.length).toBeLessThanOrEqual(40);
    expect(expanded.length).toBeGreaterThanOrEqual(70);
  });

  it("toggles collapse and expands ancestors for search hits", () => {
    const map = loadPatternMapMock();
    let state = initialCollapseState(map.nodes);
    const parent = map.nodes.find((n) => n.collapsedByDefault && n.childCount > 0)!;
    expect(collectVisibleNodes(map.nodes, state).some((n) => n.parentId === parent.id)).toBe(
      false,
    );
    state = setCollapsed(state, parent.id, false);
    expect(collectVisibleNodes(map.nodes, state).some((n) => n.parentId === parent.id)).toBe(
      true,
    );
    const leaf = map.nodes.find((n) => n.parentId === parent.id)!;
    state = initialCollapseState(map.nodes);
    state = expandAncestorsForNode(map.nodes, state, leaf.id);
    expect(state[parent.id]).toBe(false);
    expect(findMatchingNodeIds(map.nodes, "中点").length).toBeGreaterThan(0);
  });
});

describe("patternMapLayout", () => {
  it("places visible nodes without overlapping ids", () => {
    const map = loadPatternMapMock();
    const visible = collectVisibleNodes(map.nodes, initialCollapseState(map.nodes));
    const layout = layoutPatternTree(visible);
    expect(layout.nodes.length).toBe(visible.length);
    expect(new Set(layout.nodes.map((n) => n.id)).size).toBe(visible.length);
    expect(layout.width).toBeGreaterThan(0);
    expect(layout.height).toBeGreaterThan(0);
  });
});

describe("evidenceDeepLink", () => {
  it("builds chapter/scene/paragraph deep links", () => {
    const map = loadPatternMapMock();
    const ref = Object.values(map.evidenceByNodeId!)[0]![0]!;
    const params = buildEvidenceDeepLinkParams(ref);
    expect(params.get("chapter")).toBe(String(ref.chapterId));
    expect(params.get("paragraph")).toBe(ref.paragraphId);
    expect(params.get("paragraphContentHash")).toBe(ref.paragraphContentHash);
    expect(evidenceDeepLinkHref(map.bookId, ref)).toContain(`/books/${map.bookId}?`);
    expect(CURRENT_EVIDENCE_LOCATE_CAPABILITY.canJumpParagraph).toBe(true);
    expect(CURRENT_EVIDENCE_LOCATE_CAPABILITY.canValidateContentHash).toBe(false);
  });
});
