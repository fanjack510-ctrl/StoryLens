/**
 * 钩子回收的排版 (CHG-20260815-102).
 *
 * Three measured problems on 《我不是戏神》第一章, all of them about what the layout chose to
 * spend its height on:
 *
 * 1. The question — the only content on the card — arrived pre-cut at 18 characters, so it
 *    read 「首段即抛出'我是谁'的疑问，第二段…」: the setup, with the question removed. The three
 *    metadata rows under it were rendered in full.
 * 2. `role` is a lookup on `status` (readerQuestionRoleOf). On three cards that is six rows
 *    of the same fact stated twice.
 * 3. The six scene labels were drawn three times: the panel's own S1–S6 trajectory, the
 *    diagnosis band (whose hook labels ARE that trajectory's short_label), and the dot rail.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { HookPayoffTimeline } from "./HookPayoffTimeline";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { buildReaderQuestionCards } from "./chapterHookSimplification";
import type { NarrativeLoopView } from "./chapterHookSimplification";

afterEach(() => {
  cleanup();
  document.getElementById("journey-overlay-root")?.remove();
});

// A question long enough that the 18-char identity cut visibly destroys it.
const LONG_QUESTION = "少年在雨夜回到早已烧毁的旧宅，他到底是谁，又为什么记得这里的每一块砖";

function loopWithLongQuestion(): NarrativeLoopView {
  return {
    loop_id: "loop-long",
    question: LONG_QUESTION,
    hook: [{ scene_ordinal: 1, level: 4, summary: "开场抛出身份疑问" }],
    developments: [{ scene_ordinal: 3 }],
    payoffs: [],
    evidence: ["B0010-C0002-P0001"],
  } as unknown as NarrativeLoopView;
}

describe("读者最想知道：问题是内容，其余是标签", () => {
  it("puts the uncut question on the card and keeps the short form for chips", () => {
    const [card] = buildReaderQuestionCards([loopWithLongQuestion()], 6);
    expect(card.question_full).toBe(LONG_QUESTION);
    // The identity form is still cut — chips and titles depend on it.
    expect(card.question.length).toBeLessThan(card.question_full.length);
    expect(card.question).toMatch(/…$/);
  });

  it("renders the full question, not the 18-char identity form", () => {
    render(
      <HookPayoffTimeline
        visualization={buildFixture13Scenes()}
        selectedSceneOrdinal={1}
        onSelectScene={vi.fn()}
      />,
    );
    const texts = screen.getAllByTestId("hook-chapter-question-text");
    expect(texts).toHaveLength(3);
    texts.forEach((node) => {
      // Whatever the length, the card must show what it has rather than an ellipsis stub,
      // and must carry the whole thing in the tooltip for the CSS clamp case.
      expect(node.getAttribute("title")).toBeTruthy();
      expect(node.textContent).toBe(node.getAttribute("title"));
    });
  });

  it("states the status once instead of twice", () => {
    render(
      <HookPayoffTimeline
        visualization={buildFixture13Scenes()}
        selectedSceneOrdinal={1}
        onSelectScene={vi.fn()}
      />,
    );
    // role is derivable from status; it survives on the model and in the tooltip, not as a
    // third line of card face.
    expect(screen.queryByTestId("hook-chapter-question-role")).not.toBeInTheDocument();
    const cards = screen.getAllByTestId("hook-chapter-question-card");
    expect(cards).toHaveLength(3);
    cards.forEach((card) => {
      const status = within(card).getByTestId("hook-chapter-question-status");
      expect(status.getAttribute("title")).toBeTruthy();
      // Status and trail share one line; the card is two rows, not four.
      expect(within(card).getByTestId("hook-chapter-question-trail")).toBeInTheDocument();
    });
  });
});

describe("场景标签只画一遍", () => {
  const renderAt = (search: string) =>
    render(
      <MemoryRouter initialEntries={[search]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );

  it("drops the diagnosis band on the hook lens, where it duplicates the trajectory", () => {
    renderAt("/?overview=curve&lens=hook_payoff&metric=hook");
    expect(screen.queryByTestId("journey-diagnosis-band")).not.toBeInTheDocument();
    // The surviving row is the one that carries stage bands, S-ids and click targets.
    expect(screen.getByTestId("journey-rhythm-strip")).toBeInTheDocument();
  });

  it("keeps the band on every other lens", () => {
    renderAt("/?overview=curve");
    expect(screen.getByTestId("journey-diagnosis-band")).toBeInTheDocument();
  });
});

describe("「读者最想知道」不该显示「这里没有钩子」", () => {
  // Verbatim from the three analysed books. The `question` field holds the model's scoring
  // rationale rather than a question, negatives included, and it was rendered as-is.
  const ABSENCE = [
    "场景开头无新钩子，仅延续前文。？",
    "开篇的悠长情绪和结尾的自嘲有一定余味，但不足以构成强烈钩子。？",
    "场景开头没有强钩子，仅以于小乐吟诗引入，缺乏吸引力。？",
  ];
  const REAL = [
    "无钥匙的障碍在第二段出现，构成小钩子，但非强悬念。？",
    "首段即抛出'我是谁'的疑问，第二段雷声和朱红人影营造强烈悬念，读者无划走窗口。？",
    "父母见鬼般的表情强烈激发读者好奇：为何父母如此惊恐？",
  ];
  const cardsFor = (question: string) =>
    buildReaderQuestionCards(
      [
        {
          loop_id: "L1",
          question,
          hook: [{ scene_ordinal: 1, level: 4 }],
          developments: [],
          payoffs: [],
          evidence: [],
        } as unknown as NarrativeLoopView,
      ],
      6,
    );

  it.each(ABSENCE)("drops %s", (question) => {
    expect(cardsFor(question)).toHaveLength(0);
  });

  it.each(REAL)("keeps %s", (question) => {
    expect(cardsFor(question)).toHaveLength(1);
  });

  it("keeps a weak-but-real hook — the filter is about absence, not low scores", () => {
    const [card] = cardsFor("无钥匙的障碍在第二段出现，构成小钩子，但非强悬念。？");
    expect(card.question_full).toContain("构成小钩子");
  });

  it("strips the question mark appended after a full stop, and only then", () => {
    const [statement] = cardsFor("首段即抛出'我是谁'的疑问，读者无划走窗口。？");
    expect(statement.question_full.endsWith("。")).toBe(true);
    const [real] = cardsFor("父母见鬼般的表情强烈激发读者好奇：为何父母如此惊恐？");
    expect(real.question_full.endsWith("？")).toBe(true);
  });
});
