import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadPatternMapMock } from "../mocks/loadPatternMapMock";
import { PatternMapPrototype } from "./PatternMapPrototype";

afterEach(() => {
  cleanup();
});

describe("PatternMapPrototype spike", () => {
  it("renders ~40 default nodes and expands toward ~80", () => {
    const map = loadPatternMapMock();
    const { container } = render(<PatternMapPrototype map={map} />);
    const root = within(container).getByTestId("pattern-map-prototype");
    const defaultCount = Number(root.getAttribute("data-visible-count"));
    expect(defaultCount).toBeGreaterThanOrEqual(30);
    expect(defaultCount).toBeLessThanOrEqual(40);
    expect(within(root).getByTestId("pattern-map-canvas")).toBeInTheDocument();
    expect(within(root).getByTestId("pattern-map-detail")).toBeInTheDocument();

    fireEvent.click(within(root).getByTestId("pattern-map-expand-all"));
    const expanded = Number(
      within(container).getByTestId("pattern-map-prototype").getAttribute("data-visible-count"),
    );
    expect(expanded).toBeGreaterThanOrEqual(70);
    expect(expanded).toBe(map.nodes.length);
  });

  it("selects a node and shows detail + evidence when available", () => {
    const map = loadPatternMapMock();
    const { container } = render(<PatternMapPrototype map={map} />);
    const root = within(container).getByTestId("pattern-map-prototype");
    fireEvent.click(within(root).getByTestId("pattern-map-node-n_tp_midpoint"));
    expect(within(root).getByTestId("pattern-map-detail-title")).toHaveTextContent("中点翻转");
    const evidenceCount = map.evidenceByNodeId?.n_tp_midpoint?.length ?? 0;
    expect(evidenceCount).toBeGreaterThan(0);
    expect(within(root).getByTestId("pattern-map-evidence-list").querySelectorAll("li").length).toBe(
      evidenceCount,
    );
  });

  it("collapses and expands a parent node", () => {
    const map = loadPatternMapMock();
    const { container } = render(<PatternMapPrototype map={map} />);
    const root = within(container).getByTestId("pattern-map-prototype");
    expect(within(root).getByTestId("pattern-map-node-n_stage_setup")).toHaveAttribute(
      "data-collapsed",
      "false",
    );
    fireEvent.click(within(root).getByTestId("pattern-map-toggle-n_stage_setup"));
    expect(within(root).getByTestId("pattern-map-node-n_stage_setup")).toHaveAttribute(
      "data-collapsed",
      "true",
    );
    fireEvent.click(within(root).getByTestId("pattern-map-toggle-n_stage_setup"));
    expect(within(root).getByTestId("pattern-map-node-n_stage_setup")).toHaveAttribute(
      "data-collapsed",
      "false",
    );
  });

  it("supports search locate and theme toggle", () => {
    const map = loadPatternMapMock();
    const onThemeChange = vi.fn();
    const { container } = render(
      <PatternMapPrototype map={map} theme="light" onThemeChange={onThemeChange} />,
    );
    const root = within(container).getByTestId("pattern-map-prototype");
    fireEvent.change(within(root).getByTestId("pattern-map-search"), {
      target: { value: "至暗" },
    });
    fireEvent.click(within(root).getByTestId("pattern-map-search-next"));
    expect(within(root).getByTestId("pattern-map-detail-title")).toHaveTextContent("至暗考验");
    fireEvent.click(within(root).getByTestId("pattern-map-theme-toggle"));
    expect(onThemeChange).toHaveBeenCalledWith("dark");
  });

  it("zooms via toolbar and keeps keyboard focus target", () => {
    const map = loadPatternMapMock();
    const { container } = render(<PatternMapPrototype map={map} />);
    const root = within(container).getByTestId("pattern-map-prototype");
    root.focus();
    fireEvent.click(within(root).getByTestId("pattern-map-zoom-in"));
    expect(within(root).getByTestId("pattern-map-hud").textContent).toMatch(/缩放 1\.10/);
    fireEvent.keyDown(root, { key: "-" });
    expect(within(root).getByTestId("pattern-map-hud").textContent).toMatch(/缩放 1\.00/);
  });
});
