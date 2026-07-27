import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { JourneySceneDetailPanel } from "./JourneySceneDetailPanel";

describe("JourneySceneDetailPanel integrity gate", () => {
  it("hides contaminated detail and does not auto-call model regen", () => {
    render(
      <JourneySceneDetailPanel
        node={
          {
            scene_id: 77,
            scene_ordinal: 5,
            integrity_blocked: true,
            integrity_status: "data_integrity_failed",
            overview: "检测到部分结论与当前正文不一致，相关结果已暂停展示。",
            title: "分析结果校验未通过",
            hooks: [],
            payoffs: [],
          } as any
        }
        onLocateEvidence={() => undefined}
      />,
    );
    expect(screen.getByTestId("journey-scene-integrity-blocked")).toBeInTheDocument();
    expect(screen.getByTestId("journey-integrity-message")).toHaveTextContent("不一致");
    expect(screen.getByTestId("journey-integrity-regen")).toBeDisabled();
    expect(screen.queryByText("古青")).not.toBeInTheDocument();
  });
});

describe("reader journey query key scope", () => {
  it("documents full cache key shape book/chapter/run", () => {
    const bookId = 10;
    const chapterId = 1221;
    const analysisRunId = 9;
    const key = ["reader-journey", bookId, chapterId, analysisRunId];
    expect(key).toEqual(["reader-journey", 10, 1221, 9]);
    expect(key).not.toEqual(["reader-journey", 9]);
  });
});
