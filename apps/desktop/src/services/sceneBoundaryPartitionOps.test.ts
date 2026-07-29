import { describe, expect, it } from "vitest";
import {
  addSceneBoundary,
  canSplitAfterParagraph,
  mergeSceneBoundary,
} from "./sceneBoundaryPartitionOps";

describe("sceneBoundaryPartitionOps split", () => {
  const ids = ["P1", "P2", "P3", "P4", "P5", "P6"];

  it("splits 1-6 at 3/4 into 1-3 and 4-6", () => {
    const scenes = [
      {
        scene_order: 1,
        start_paragraph_id: "P1",
        end_paragraph_id: "P6",
        included_in_journey: true,
      },
    ];
    const next = addSceneBoundary(scenes, "P3", ids);
    expect(next).toEqual([
      {
        scene_order: 1,
        start_paragraph_id: "P1",
        end_paragraph_id: "P3",
        included_in_journey: true,
      },
      {
        scene_order: 2,
        start_paragraph_id: "P4",
        end_paragraph_id: "P6",
        included_in_journey: true,
      },
    ]);
  });

  it("inherits included=false and merge restores", () => {
    const scenes = [
      {
        scene_order: 1,
        start_paragraph_id: "P1",
        end_paragraph_id: "P6",
        included_in_journey: false,
      },
    ];
    const split = addSceneBoundary(scenes, "P2", ids);
    expect(split.every((s) => s.included_in_journey === false)).toBe(true);
    const merged = mergeSceneBoundary(split, 0, ids);
    expect(merged).toHaveLength(1);
    expect(merged[0].included_in_journey).toBe(false);
  });

  it("blocks single-paragraph and existing boundary gaps", () => {
    expect(
      canSplitAfterParagraph({
        paragraphId: "P1",
        sceneParagraphIds: ["P1"],
        chapterParagraphIds: ids,
        boundaryAfterParagraphIds: new Set(),
      }),
    ).toBe(false);
    expect(
      canSplitAfterParagraph({
        paragraphId: "P3",
        sceneParagraphIds: ["P1", "P2", "P3", "P4"],
        chapterParagraphIds: ids,
        boundaryAfterParagraphIds: new Set(["P3"]),
      }),
    ).toBe(false);
    expect(
      canSplitAfterParagraph({
        paragraphId: "P2",
        sceneParagraphIds: ["P1", "P2", "P3", "P4"],
        chapterParagraphIds: ids,
        boundaryAfterParagraphIds: new Set(["P4"]),
      }),
    ).toBe(true);
  });
});
