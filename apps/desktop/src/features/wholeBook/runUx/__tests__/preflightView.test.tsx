import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, within } from "@testing-library/react";
import { WholeBookPreflightView } from "../components/WholeBookPreflightView";
import { WholeBookModeSelector } from "../components/WholeBookModeSelector";
import { WholeBookModuleSelector } from "../components/WholeBookModuleSelector";
import { WholeBookStagePlanPreview } from "../components/WholeBookStagePlanPreview";
import {
  FIXTURE_PREFLIGHT_ENRICHED,
  FIXTURE_STAGE_PLAN_ROWS,
} from "../fixtures/preflightFixtures";
import { WHOLE_BOOK_MODULE_KEYS } from "../../contracts/keys";
import { resolveModulesWithDependencies } from "../../contracts/guards";

afterEach(() => {
  cleanup();
});

describe("Preflight UX components", () => {
  it("renders Native mode selection", () => {
    const onChange = vi.fn();
    render(
      <WholeBookModeSelector
        value="whole_book_native"
        supportedModes={["whole_book_native", "whole_book_enhanced"]}
        onChange={onChange}
      />,
    );
    const native = screen.getByTestId("mode-option-whole_book_native");
    expect(native).toHaveAttribute("data-selected", "true");
    expect(native).toHaveTextContent("完整正文 Snapshot");
  });

  it("renders Enhanced mode with coverage", () => {
    render(
      <WholeBookModeSelector
        value="whole_book_enhanced"
        supportedModes={["whole_book_native", "whole_book_enhanced"]}
        sourceCoverage={FIXTURE_PREFLIGHT_ENRICHED.source_coverage}
        onChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("enhanced-coverage")).toBeInTheDocument();
    expect(screen.getByTestId("enhanced-coverage")).toHaveTextContent("降级");
  });

  it("disables unsupported mode from backend supported_modes", () => {
    render(
      <WholeBookModeSelector
        value="whole_book_native"
        supportedModes={["whole_book_native"]}
        disabledReasons={{
          whole_book_enhanced: "CAPABILITY_MODE_NOT_SUPPORTED",
        }}
        onChange={() => undefined}
      />,
    );
    const enhanced = screen.getByTestId("mode-option-whole_book_enhanced");
    expect(enhanced).toBeDisabled();
    expect(enhanced).toHaveTextContent("不可用");
  });

  it("lists all 11 modules and shows auto dependency notes", () => {
    const resolved = resolveModulesWithDependencies(["diagnostics"]);
    render(
      <WholeBookModuleSelector
        requestedModules={["diagnostics"]}
        resolvedModules={resolved.modules}
        autoFillNotes={resolved.notes}
        onChange={() => undefined}
      />,
    );
    for (const key of WHOLE_BOOK_MODULE_KEYS) {
      expect(screen.getByTestId(`module-item-${key}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("diagnostics-dependency-hint")).toBeInTheDocument();
    expect(screen.getByTestId("resolved-stages")).toHaveTextContent(
      "analyze_structure",
    );
    expect(screen.getByTestId("resolved-modules")).not.toHaveTextContent(
      "analyze_structure",
    );
  });

  it("keeps module/stage separation visible", () => {
    const { container } = render(
      <WholeBookModuleSelector
        requestedModules={["book_overview"]}
        resolvedModules={["book_overview"]}
        onChange={() => undefined}
      />,
    );
    expect(within(container).getByText(/模块与 Stage 分离/)).toBeInTheDocument();
    expect(within(container).getByTestId("resolved-stages").textContent).not.toEqual(
      within(container).getByTestId("resolved-modules").textContent,
    );
  });

  it("shows stage plan with auto-fill visual distinction", () => {
    render(<WholeBookStagePlanPreview rows={FIXTURE_STAGE_PLAN_ROWS} />);
    expect(
      screen.getByTestId("stage-plan-resolve_entities"),
    ).toHaveAttribute("data-auto-filled", "true");
    expect(screen.getByText("建立全文索引")).toBeInTheDocument();
    expect(screen.queryByText(/prompt/i)).not.toBeInTheDocument();
  });

  it("disables start button, shows blocking reasons, no force start", () => {
    render(
      <WholeBookPreflightView
        model={FIXTURE_PREFLIGHT_ENRICHED}
        supportedModes={["whole_book_native", "whole_book_enhanced"]}
        stagePlanRows={FIXTURE_STAGE_PLAN_ROWS}
        onModeChange={() => undefined}
        onModulesChange={() => undefined}
        onRefresh={() => undefined}
      />,
    );
    const start = screen.getByTestId("start-whole-book-analysis");
    expect(start).toBeDisabled();
    expect(start).toHaveAttribute("data-force-start", "false");
    expect(screen.queryByTestId("force-start")).not.toBeInTheDocument();
    expect(screen.getByTestId("run-creation-enabled")).toHaveTextContent(
      "false",
    );
    expect(screen.getByTestId("blocking-reasons-list")).toHaveTextContent(
      "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED",
    );
  });

  it("locks required auto-filled dependency modules from uncheck", () => {
    const onChange = vi.fn();
    render(
      <WholeBookModuleSelector
        requestedModules={["storylines"]}
        resolvedModules={["storylines", "structure_stages"]}
        onChange={onChange}
      />,
    );
    const locked = screen.getByTestId("module-check-structure_stages");
    expect(locked).toBeDisabled();
    expect(screen.getByTestId("module-item-structure_stages")).toHaveAttribute(
      "data-required-locked",
      "true",
    );
    fireEvent.click(locked);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("supports keyboard focus on mode cards", () => {
    render(
      <WholeBookModeSelector
        value="whole_book_native"
        supportedModes={["whole_book_native", "whole_book_enhanced"]}
        onChange={() => undefined}
      />,
    );
    const native = screen.getByTestId("mode-option-whole_book_native");
    native.focus();
    expect(document.activeElement).toBe(native);
    fireEvent.keyDown(native, { key: "Enter" });
  });
});
