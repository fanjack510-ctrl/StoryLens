import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyEntry } from "./ReaderJourneyEntry";

afterEach(() => cleanup());

describe("ReaderJourneyEntry", () => {
  it("shows analyze entry when journey result is missing", () => {
    const onAnalyze = vi.fn();
    render(
      <ReaderJourneyEntry hasJourney={false} onAnalyze={onAnalyze} onView={vi.fn()} />,
    );
    const btn = screen.getByTestId("reader-journey-entry-analyze");
    expect(btn).toHaveTextContent("分析读者旅程");
    fireEvent.click(btn);
    expect(onAnalyze).toHaveBeenCalledTimes(1);
  });

  it("shows view entry when journey result exists", () => {
    const onView = vi.fn();
    render(
      <ReaderJourneyEntry hasJourney onAnalyze={vi.fn()} onView={onView} />,
    );
    const btn = screen.getByTestId("reader-journey-entry-view");
    expect(btn).toHaveTextContent("查看读者旅程");
    fireEvent.click(btn);
    expect(onView).toHaveBeenCalledTimes(1);
  });
});
