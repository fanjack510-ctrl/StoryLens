import type { ReactElement, ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JourneyDetailErrorBoundary } from "./JourneyDetailErrorBoundary";
import {
  HookList,
  ReaderQuestionList,
  TechniqueList,
  WritingTakeawayList,
} from "./sceneDetailFields";
import { normalizeWritingTakeaway, renderFallbackValue } from "./safeRender";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_ReaderJourney_v1.1.png",
    }),
  };
});

afterEach(cleanup);

function renderJourney(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("writing takeaways and structured detail fields", () => {
  it("renders writing_takeaways object fields", () => {
    render(
      <WritingTakeawayList
        items={[
          {
            summary: "用动作埋身份疑点",
            applicable_when: "开场",
            avoid_when: "信息过载时",
          },
        ]}
      />,
    );
    const item = screen.getByTestId("journey-takeaway-item");
    expect(item).toHaveTextContent("用动作埋身份疑点");
    expect(item).toHaveTextContent("适用：开场");
    expect(item).toHaveTextContent("慎用：信息过载时");
  });

  it("renders empty writing takeaways message", () => {
    render(<WritingTakeawayList items={[]} />);
    expect(screen.getByText("暂无可迁移写作启示")).toBeInTheDocument();
  });

  it("compatibly renders legacy string takeaways", () => {
    render(<WritingTakeawayList items={["控制信息密度"]} />);
    expect(screen.getByTestId("journey-takeaway-item")).toHaveTextContent("控制信息密度");
    expect(normalizeWritingTakeaway("控制信息密度")).toEqual({ summary: "控制信息密度" });
  });

  it("does not pass unknown objects as React children", () => {
    render(<WritingTakeawayList items={[{ foo: 1 }]} />);
    expect(screen.getByText("该分析项结构暂不支持")).toBeInTheDocument();
    expect(renderFallbackValue({ foo: 1 })).toBe("该分析项结构暂不支持");
  });

  it("renders techniques and hooks as structured objects", () => {
    render(
      <>
        <TechniqueList
          items={[
            {
              name: "悬念递进",
              mechanism: "延迟揭晓",
              reader_effect: "提高好奇",
              transfer_formula: "已知-缺口-兑现",
              risk: "拖沓",
            },
          ]}
        />
        <HookList
          items={[
            {
              type: "mystery",
              summary: "章末钩子",
              strength: 90,
              known: "已回答",
              gap: "身份未知",
              continue_drive: "追问",
              next_handoff: "下一场对话",
            },
          ]}
        />
        <ReaderQuestionList
          items={[
            {
              question: "少年是谁？",
              strength: 80,
              origin: "created",
            },
          ]}
        />
      </>,
    );
    expect(screen.getByTestId("journey-techniques")).toHaveTextContent("悬念递进");
    expect(screen.getByTestId("journey-hooks")).toHaveTextContent("章末钩子");
    expect(screen.getByTestId("journey-reader-questions")).toHaveTextContent("少年是谁？");
  });

  it("opens Scene 1 and Scene 14 drawers without crashing", () => {
    const visualization = buildMockReaderJourneyVisualization();
    const { rerender } = renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={1}
      />,
    );
    expect(screen.getByTestId("journey-detail-drawer")).toHaveTextContent(/场景01/);
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={14}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-detail-drawer")).toHaveTextContent(/场景14/);
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toBeInTheDocument();
  });

  it("error boundary catches detail render crashes", () => {
    function Boom(): ReactNode {
      throw new Error("detail boom");
    }
    render(
      <JourneyDetailErrorBoundary>
        <Boom />
      </JourneyDetailErrorBoundary>,
    );
    expect(screen.getByTestId("journey-detail-error")).toHaveTextContent(
      "该Scene的部分分析内容无法显示。",
    );
  });
});
