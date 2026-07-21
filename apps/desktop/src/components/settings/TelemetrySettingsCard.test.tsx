import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { TelemetrySettingsCard } from "./TelemetrySettingsCard";
import { useTelemetryStore } from "../../stores/telemetry";

describe("TelemetrySettingsCard", () => {
  beforeEach(() => {
    localStorage.clear();
    useTelemetryStore.setState({ consent: "UNKNOWN", installIdPreview: null });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders consent switch off by default", () => {
    render(<TelemetrySettingsCard />);
    const toggle = screen.getByRole("switch", { name: "允许匿名使用统计" });
    expect(toggle).not.toBeChecked();
    expect(screen.getByTestId("telemetry-not-collected")).toBeInTheDocument();
  });

  it("shows privacy doc reference", () => {
    render(<TelemetrySettingsCard />);
    expect(screen.getByTestId("telemetry-privacy-link")).toHaveTextContent("telemetry-plan.md");
  });

  it("enables consent when user toggles on", () => {
    render(<TelemetrySettingsCard />);
    fireEvent.click(screen.getByRole("switch", { name: "允许匿名使用统计" }));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("ENABLED");
  });
});
