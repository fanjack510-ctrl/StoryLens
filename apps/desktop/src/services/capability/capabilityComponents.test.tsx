import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  CapabilityGate,
  CapabilityStatusBadge,
  ProFeaturePreviewCard,
} from "../../features/capability";
import { getCapabilityPresentation } from "../capability/presentation";

afterEach(() => {
  cleanup();
});

describe("Capability presentation components", () => {
  it("CapabilityGate shows deny reason instead of only hiding children", () => {
    const presentation = getCapabilityPresentation("whole_book_analysis", {
      capabilityKey: "whole_book_analysis",
      allowed: false,
      reasonCode: "CAPABILITY_NOT_LICENSED",
      availability: "unavailable",
    });
    render(
      <CapabilityGate presentation={presentation}>
        <button type="button">Run</button>
      </CapabilityGate>,
    );
    expect(screen.getByTestId("capability-gate")).toHaveAttribute("data-disabled", "true");
    expect(screen.getByTestId("capability-reason-panel")).toHaveTextContent("整书分析");
    expect(screen.getByTestId("capability-gate-children")).toHaveAttribute(
      "data-blocked",
      "true",
    );
    expect(screen.getByTestId("capability-gate-upgrade")).toBeInTheDocument();
  });

  it("CapabilityStatusBadge distinguishes preview and available", () => {
    const { rerender } = render(
      <CapabilityStatusBadge capabilityKey="story_lab" state="preview" />,
    );
    expect(screen.getByTestId("capability-status-badge")).toHaveAttribute(
      "data-state",
      "preview",
    );
    rerender(<CapabilityStatusBadge capabilityKey="story_lab" state="available" />);
    expect(screen.getByTestId("capability-status-badge")).toHaveAttribute(
      "data-state",
      "available",
    );
  });

  it("foundation capability badge is not shown as locked paywall", () => {
    render(
      <CapabilityStatusBadge
        capabilityKey="narrative_asset_library"
        state="not_shipped"
      />,
    );
    const badge = screen.getByTestId("capability-status-badge");
    expect(badge).toHaveAttribute("data-foundation", "true");
    expect(badge).toHaveTextContent("基础能力");
  });

  it("supports keyboard focus on gate and preview card", () => {
    const preview = getCapabilityPresentation("story_lab", {
      capabilityKey: "story_lab",
      allowed: true,
      reasonCode: "CAPABILITY_PREVIEW_ONLY",
      availability: "preview",
      previewOnly: true,
      displayMessage: "当前为预览状态，完整能力尚未开放",
    });
    render(<ProFeaturePreviewCard presentation={preview} />);
    const card = screen.getByTestId("pro-feature-preview-card");
    card.focus();
    expect(card).toHaveFocus();
    fireEvent.keyDown(card, { key: "Tab" });
    expect(screen.getByTestId("capability-preview-action")).toBeInTheDocument();
  });

  it("light/dark theme tokens apply via data-theme without crashing", () => {
    const presentation = getCapabilityPresentation("advanced_export", {
      capabilityKey: "advanced_export",
      allowed: false,
      reasonCode: "CAPABILITY_NOT_SHIPPED",
      availability: "unavailable",
    });
    const { container, rerender } = render(
      <div data-theme="light">
        <CapabilityGate presentation={presentation} />
      </div>,
    );
    expect(container.querySelector(".capability-gate")).toBeTruthy();
    rerender(
      <div data-theme="dark">
        <CapabilityGate presentation={presentation} />
      </div>,
    );
    expect(container.querySelector('[data-theme="dark"] .capability-gate')).toBeTruthy();
  });
});
