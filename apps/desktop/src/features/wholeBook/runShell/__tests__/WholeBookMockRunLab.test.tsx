import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WholeBookMockRunLab } from "../lab/WholeBookMockRunLab";
import { MockPartialResultsPanel } from "../lab/MockPartialResultsPanel";
import { MockRunControls } from "../controls/MockRunControls";
import { presentMockRunError } from "../client/errors";
import { MockRunClientError } from "../client/types";
import { WHOLE_BOOK_MOCK_RUN_LAB_PATH } from "../lab/isolatedRoute";
import { RUN_CREATE_ENABLED_IN_CLIENT } from "../../runUx/constants";
import {
  MOCK_CREATE_RESULT_DUP,
  MOCK_CREATE_RESULT_NEW,
  MOCK_FIXTURE_CANCELLED,
  MOCK_FIXTURE_FAILED,
  MOCK_FIXTURE_INTERRUPTED,
  MOCK_FIXTURE_PAUSED,
  MOCK_FIXTURE_RUNNING,
  MOCK_MODULE_ENVELOPE,
  MOCK_RESULT_INDEX,
  mockActionResult,
} from "./fixtures";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function makeClient(overrides: Record<string, unknown> = {}) {
  return {
    create: vi.fn(async () => MOCK_CREATE_RESULT_NEW) as ReturnType<typeof vi.fn>,
    get: vi.fn(async () => MOCK_FIXTURE_RUNNING) as ReturnType<typeof vi.fn>,
    getStages: vi.fn(async () => ({
      run_id: 101,
      mock: true as const,
      non_production: true as const,
      stages: MOCK_FIXTURE_RUNNING.stages,
      updated_at: MOCK_FIXTURE_RUNNING.updated_at,
      version: 3,
    })),
    pause: vi.fn(async () => mockActionResult("pause", "paused")) as ReturnType<
      typeof vi.fn
    >,
    resume: vi.fn(async () => mockActionResult("resume", "running")) as ReturnType<
      typeof vi.fn
    >,
    cancel: vi.fn(async () =>
      mockActionResult("cancel", "cancelled"),
    ) as ReturnType<typeof vi.fn>,
    retryStage: vi.fn(async () =>
      mockActionResult("retry", "running"),
    ) as ReturnType<typeof vi.fn>,
    getCalledPaths: () => [],
    clearCalledPaths: () => undefined,
    formalCreatePath: "/api/v1/books/{book_id}/whole-book-runs",
    labBase: "/api/v1/labs/whole-book-runs",
    ...overrides,
  };
}

describe("WholeBookMockRunLab", () => {
  it("hides entirely in production", () => {
    const { container } = render(
      <WholeBookMockRunLab
        labEnabled
        appEnvironment="production"
        useFixtures
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows disabled reason when lab disabled", () => {
    render(
      <WholeBookMockRunLab
        labEnabled={false}
        appEnvironment="development"
        useFixtures
      />,
    );
    expect(screen.getByTestId("mock-lab-disabled")).toHaveTextContent(
      "Mock Lab 已禁用",
    );
  });

  it("shows mock banners and keeps production start disabled", async () => {
    render(
      <WholeBookMockRunLab labEnabled appEnvironment="development" useFixtures />,
    );
    expect(screen.getByTestId("mock-non-production-banner")).toHaveTextContent(
      "开发验证，不是真实分析",
    );
    expect(screen.getByTestId("mock-badge-banner")).toHaveTextContent("mock");
    expect(screen.getByTestId("start-whole-book-analysis")).toBeDisabled();
    expect(screen.getByTestId("start-mock-whole-book-run")).toBeEnabled();
    expect(RUN_CREATE_ENABLED_IN_CLIENT).toBe(false);
  });

  it("creates mock run, prevents double click, handles duplicate", async () => {
    const client = makeClient({
      create: vi
        .fn()
        .mockResolvedValueOnce(MOCK_CREATE_RESULT_NEW)
        .mockResolvedValueOnce(MOCK_CREATE_RESULT_DUP),
    });
    render(
      <WholeBookMockRunLab
        labEnabled
        appEnvironment="development"
        useFixtures
        client={client as never}
      />,
    );
    const btn = screen.getByTestId("start-mock-whole-book-run");
    fireEvent.click(btn);
    fireEvent.click(btn);
    await waitFor(() => expect(client.create).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("mock-run-progress-panel")).toBeInTheDocument(),
    );
    expect(client.create.mock.calls[0]?.[0]).toMatchObject({
      book_id: 1,
      book_snapshot_id: 11,
      mock_profile: "deterministic_minimal",
      idempotency_key: expect.stringContaining("mock-create"),
    });
    expect(JSON.stringify(client.create.mock.calls[0]?.[0])).not.toContain(
      "full_text",
    );
  });

  it("create failure does not enter progress", async () => {
    const client = makeClient({
      create: vi.fn(async () => {
        throw new MockRunClientError(
          "lab disabled",
          "MOCK_LAB_DISABLED",
          403,
        );
      }),
    });
    render(
      <WholeBookMockRunLab
        labEnabled
        appEnvironment="development"
        useFixtures
        client={client as never}
      />,
    );
    fireEvent.click(screen.getByTestId("start-mock-whole-book-run"));
    await waitFor(() =>
      expect(screen.getByTestId("mock-create-error")).toHaveTextContent(
        "Mock Lab 已禁用",
      ),
    );
    expect(screen.queryByTestId("mock-run-progress-panel")).not.toBeInTheDocument();
  });

  it("shows duplicate notice when created=false", async () => {
    const client = makeClient({
      create: vi.fn(async () => MOCK_CREATE_RESULT_DUP),
    });
    render(
      <WholeBookMockRunLab
        labEnabled
        appEnvironment="development"
        useFixtures
        client={client as never}
      />,
    );
    fireEvent.click(screen.getByTestId("start-mock-whole-book-run"));
    await waitFor(() =>
      expect(screen.getByTestId("duplicate-run-notice")).toHaveTextContent(
        "已复用既有 Mock Run",
      ),
    );
  });

  it("supports theme toggle and keyboard focus", () => {
    render(
      <WholeBookMockRunLab labEnabled appEnvironment="development" useFixtures />,
    );
    const root = screen.getByTestId("whole-book-mock-run-lab");
    expect(root).toHaveAttribute("data-theme", "light");
    const toggle = screen.getByTestId("mock-theme-toggle");
    toggle.focus();
    expect(document.activeElement).toBe(toggle);
    fireEvent.click(toggle);
    expect(root).toHaveAttribute("data-theme", "dark");
  });

  it("proves isolated route constant is not product nav", () => {
    expect(WHOLE_BOOK_MOCK_RUN_LAB_PATH).toBe("/dev/whole-book-mock-run-lab");
  });
});

describe("MockRunControls", () => {
  it("pause/resume/retry/cancel honor allowed_actions and confirm", async () => {
    const client = makeClient({
      get: vi
        .fn()
        .mockResolvedValueOnce(MOCK_FIXTURE_PAUSED)
        .mockResolvedValueOnce(MOCK_FIXTURE_RUNNING)
        .mockResolvedValueOnce(MOCK_FIXTURE_RUNNING)
        .mockResolvedValueOnce(MOCK_FIXTURE_CANCELLED),
    });
    const onChange = vi.fn();
    const { rerender } = render(
      <MockRunControls
        client={client as never}
        view={MOCK_FIXTURE_RUNNING}
        onViewChange={onChange}
      />,
    );
    expect(screen.getByTestId("mock-action-pause")).toBeEnabled();
    fireEvent.click(screen.getByTestId("mock-action-pause"));
    await waitFor(() => expect(client.pause).toHaveBeenCalled());
    await waitFor(() => expect(onChange).toHaveBeenCalled());

    rerender(
      <MockRunControls
        client={client as never}
        view={MOCK_FIXTURE_PAUSED}
        onViewChange={onChange}
      />,
    );
    expect(screen.getByTestId("mock-action-pause")).toBeDisabled();
    fireEvent.click(screen.getByTestId("mock-action-resume"));
    await waitFor(() => expect(client.resume).toHaveBeenCalled());

    rerender(
      <MockRunControls
        client={client as never}
        view={MOCK_FIXTURE_FAILED}
        onViewChange={onChange}
      />,
    );
    fireEvent.change(screen.getByTestId("mock-retry-stage-select"), {
      target: { value: "analyze_structure" },
    });
    expect(screen.getByTestId("retry-downstream-impact")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mock-action-retry"));
    await waitFor(() => expect(client.retryStage).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("mock-action-cancel"));
    expect(screen.getByTestId("mock-cancel-confirm")).toHaveTextContent(
      "候选结果会保留",
    );
    fireEvent.click(screen.getByTestId("mock-action-cancel-confirm"));
    await waitFor(() => expect(client.cancel).toHaveBeenCalled());
  });

  it("resume works from interrupted with same run_id", async () => {
    const client = makeClient({
      get: vi.fn(async () => MOCK_FIXTURE_RUNNING),
    });
    render(
      <MockRunControls
        client={client as never}
        view={MOCK_FIXTURE_INTERRUPTED}
        onViewChange={() => undefined}
      />,
    );
    fireEvent.click(screen.getByTestId("mock-action-resume"));
    await waitFor(() =>
      expect(client.resume).toHaveBeenCalledWith(
        101,
        expect.objectContaining({
          operation_idempotency_key: expect.stringContaining("resume"),
        }),
      ),
    );
  });
});

describe("Partial results lab", () => {
  it("marks candidate/partial/completed and keeps cancelled readable", async () => {
    const client = {
      getIndex: vi.fn(async () => MOCK_RESULT_INDEX),
      getModule: vi.fn(async () => MOCK_MODULE_ENVELOPE),
    };
    render(
      <MockPartialResultsPanel
        runId={101}
        runStatus="cancelled"
        client={client}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("partial-module-book_overview")).toHaveAttribute(
        "data-candidate",
        "true",
      ),
    );
    expect(screen.getByTestId("mock-badge-results")).toHaveTextContent("mock");
    fireEvent.click(screen.getByTestId("open-module-book_overview"));
    await waitFor(() =>
      expect(screen.getByTestId("partial-envelope-card")).toHaveTextContent(
        "candidate",
      ),
    );
    expect(client.getModule).toHaveBeenCalledWith(101, "book_overview", "candidate");
    // failed module sibling still listed
    expect(
      screen.getByTestId("partial-module-structure_stages"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("open-evidence-drawer"));
    expect(screen.getByTestId("evidence-preview-card")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("open-structure-map"));
    expect(screen.getByTestId("mock-structure-map")).toBeInTheDocument();
  });

  it("interrupted results remain readable", async () => {
    const client = {
      getIndex: vi.fn(async () => ({
        ...MOCK_RESULT_INDEX,
        run_status: "interrupted" as const,
      })),
      getModule: vi.fn(async () => MOCK_MODULE_ENVELOPE),
    };
    render(
      <MockPartialResultsPanel
        runId={101}
        runStatus="interrupted"
        client={client}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("mock-partial-results-panel")).toHaveAttribute(
        "data-run-status",
        "interrupted",
      ),
    );
  });
});

describe("Error presentation", () => {
  it("maps known codes to stable copy without stack", () => {
    const presented = presentMockRunError(
      new MockRunClientError("x", "MOCK_RUN_STATE_CONFLICT", 409),
    );
    expect(presented.title).toBe("运行状态冲突");
    expect(presented.message).not.toMatch(/at Object|stack/i);
  });
});
