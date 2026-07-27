import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { WholeBookRunProgressView } from "../components/WholeBookRunProgressView";
import { WholeBookRunActionBar } from "../components/WholeBookRunActionBar";
import { applyMockRunAction } from "../mockRunActionAdapter";
import {
  FIXTURE_RUN_FAILED_STAGE,
  FIXTURE_RUN_INTERRUPTED,
  FIXTURE_RUN_PAUSED,
  FIXTURE_RUN_RUNNING,
} from "../fixtures/runViewFixtures";

afterEach(() => {
  cleanup();
});

describe("Run progress and actions", () => {
  it("shows run status and allowed_actions from fixture", () => {
    render(
      <WholeBookRunProgressView
        view={FIXTURE_RUN_RUNNING}
        onViewChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("run-status-text")).toHaveTextContent("运行中");
    expect(screen.getByTestId("allowed-actions")).toHaveTextContent("pause");
    expect(screen.getByTestId("whole-book-run-progress-view")).toHaveAttribute(
      "data-status",
      "running",
    );
  });

  it("distinguishes interrupted from failed", () => {
    const { rerender } = render(
      <WholeBookRunProgressView
        view={FIXTURE_RUN_INTERRUPTED}
        onViewChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("whole-book-run-progress-view")).toHaveAttribute(
      "data-interrupted",
      "true",
    );
    expect(screen.getByTestId("run-status-text")).toHaveTextContent("已中断");

    rerender(
      <WholeBookRunProgressView
        view={FIXTURE_RUN_FAILED_STAGE}
        onViewChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("whole-book-run-progress-view")).toHaveAttribute(
      "data-failed",
      "true",
    );
    expect(screen.getByTestId("run-status-text")).toHaveTextContent("失败");
  });

  it("keeps completed modules when a later stage fails", () => {
    render(
      <WholeBookRunProgressView
        view={FIXTURE_RUN_FAILED_STAGE}
        onViewChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("whole-book-partial-result-notice")).toHaveTextContent(
      "book_overview",
    );
    expect(FIXTURE_RUN_FAILED_STAGE.completed_modules).toContain("book_overview");
    expect(FIXTURE_RUN_FAILED_STAGE.failed_modules).toContain("structure_stages");
  });

  it("pause only when allowed_actions includes pause", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <WholeBookRunActionBar
        view={FIXTURE_RUN_RUNNING}
        onViewChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("action-pause"));
    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls[0][0].status).toBe("paused");

    rerender(
      <WholeBookRunActionBar
        view={FIXTURE_RUN_PAUSED}
        onViewChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("action-pause")).toBeDisabled();
  });

  it("resume from paused without re-running completed stages", () => {
    const { result, next } = applyMockRunAction(FIXTURE_RUN_PAUSED, "resume");
    expect(result.ok).toBe(true);
    expect(next.status).toBe("running");
    const completed = next.stages.filter((s) => s.status === "completed");
    expect(completed.length).toBeGreaterThan(0);
    expect(
      completed.every((s) =>
        FIXTURE_RUN_PAUSED.stages.some(
          (o) => o.stage_key === s.stage_key && o.status === "completed",
        ),
      ),
    ).toBe(true);
  });

  it("retry targets failed stage only", () => {
    const { result, next } = applyMockRunAction(
      FIXTURE_RUN_FAILED_STAGE,
      "retry",
      { stage_key: "analyze_structure" },
    );
    expect(result.ok).toBe(true);
    expect(result.message).toMatch(/下游/);
    const retried = next.stages.find((s) => s.stage_key === "analyze_structure");
    expect(retried?.status).toBe("running");
    expect(retried?.attempt_count).toBe(
      FIXTURE_RUN_FAILED_STAGE.stages.find(
        (s) => s.stage_key === "analyze_structure",
      )!.attempt_count + 1,
    );
    expect(next.completed_modules).toContain("book_overview");
  });

  it("cancel requires secondary confirmation and retains candidates", () => {
    const onChange = vi.fn();
    render(
      <WholeBookRunActionBar
        view={FIXTURE_RUN_RUNNING}
        onViewChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("action-cancel"));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByTestId("cancel-confirm")).toHaveTextContent("候选结果会保留");
    fireEvent.click(screen.getByTestId("action-cancel-confirm"));
    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls[0][0].status).toBe("cancelled");
    expect(onChange.mock.calls[0][0].completed_modules).toContain(
      "book_overview",
    );
  });

  it("does not derive actions — refuses pause when not allowed", () => {
    const { result } = applyMockRunAction(FIXTURE_RUN_PAUSED, "pause");
    expect(result.ok).toBe(false);
  });
});
