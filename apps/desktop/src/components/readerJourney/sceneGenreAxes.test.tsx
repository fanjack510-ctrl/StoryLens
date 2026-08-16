/**
 * 类型专项维度与工艺缺陷在场景详情里的呈现 (CHG-20260815-100).
 *
 * These sections sit above the fold rather than inside 技术详情 on purpose: for a reader of
 * a 悬疑 book, 线索投放 and 信息公平 *are* the reading, not a diagnostic. And a book without a
 * confirmed profile must show nothing at all — an empty heading would read as a missing
 * result rather than as a question that was never asked.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JourneySceneDetailPanel } from "./JourneySceneDetailPanel";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";

afterEach(cleanup);

const visualization = buildMockReaderJourneyVisualization();
const base = visualization.scene_nodes[0];

describe("场景详情 · 类型专项", () => {
  it("shows one row per profile-selected axis, with its level and the scorer's reason", () => {
    render(
      <JourneySceneDetailPanel
        node={{
          ...base,
          genre_axes: [
            {
              key: "clue_placement",
              label: "线索投放",
              level: 4,
              evidence_paragraph_ids: ["B0010-C0002-P0031"],
              rationale: "投放了父母惊恐反应这一具体线索。",
            },
            {
              key: "fair_play",
              label: "信息公平",
              level: 2,
              evidence_paragraph_ids: [],
              rationale: "线索给过，但埋得读者几乎不可能注意到。",
            },
          ],
        }}
        onLocateEvidence={vi.fn()}
      />,
    );
    const list = screen.getByTestId("scene-genre-axis-list");
    expect(list.querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByTestId("scene-genre-axis-clue_placement")).toHaveTextContent("4 / 5");
    expect(screen.getByTestId("scene-genre-axis-fair_play")).toHaveTextContent(
      "线索给过，但埋得读者几乎不可能注意到。",
    );
  });

  it("renders nothing when the book has no confirmed profile", () => {
    render(<JourneySceneDetailPanel node={base} onLocateEvidence={vi.fn()} />);
    expect(screen.queryByTestId("scene-genre-axes")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scene-craft-flags")).not.toBeInTheDocument();
  });

  it("names a craft defect in words rather than as a score", () => {
    render(
      <JourneySceneDetailPanel
        node={{
          ...base,
          craft_flags: [
            {
              kind: "redundant_passage",
              evidence_paragraph_ids: ["B0010-C0002-P0004"],
              detail: "第 4 段与第 2 段逐字重复。",
            },
          ],
        }}
        onLocateEvidence={vi.fn()}
      />,
    );
    const flags = screen.getByTestId("scene-craft-flag-list");
    expect(flags).toHaveTextContent("重复段落");
    expect(flags).toHaveTextContent("第 4 段与第 2 段逐字重复。");
  });
});

describe("场景详情 · 焦点行", () => {
  // The panel used to stack eight blocks of equal weight and the reader could not find the
  // point. The head now answers the two questions a scene is judged on — what move it made
  // and how much of the chapter it spent — and the accumulated balance sits beside them
  // instead of in a section of its own.
  it("leads with the running balance rather than burying it in a section", () => {
    render(
      <JourneySceneDetailPanel
        node={{ ...base, open_questions: { opened: 4, closed: 3, balance: 7 } }}
        onLocateEvidence={vi.fn()}
      />,
    );
    const stats = screen.getByTestId("scene-lead-stats");
    expect(stats).toHaveTextContent("7");
    expect(stats).toHaveTextContent("开4 收3");
  });

  it("marks a balance of zero as unremarkable rather than alarming", () => {
    // A chapter that opened and closed in step is a fact about the chapter, not a warning,
    // so it must not wear the same weight as an unpaid pile of seven.
    render(
      <JourneySceneDetailPanel
        node={{ ...base, open_questions: { opened: 3, closed: 3, balance: 0 } }}
        onLocateEvidence={vi.fn()}
      />,
    );
    const zero = screen.getByTestId("scene-lead-stats").querySelector("[data-zero='true']");
    expect(zero).not.toBeNull();
  });

  it("shows a dash rather than a zero for a run from before the ledger existed", () => {
    // Absent and zero mean different things: one is "nothing owed", the other "never counted".
    render(<JourneySceneDetailPanel node={base} onLocateEvidence={vi.fn()} />);
    expect(screen.getByTestId("scene-lead-stats")).toHaveTextContent("—");
  });
});
