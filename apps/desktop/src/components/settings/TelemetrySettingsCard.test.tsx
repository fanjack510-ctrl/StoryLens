import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { TelemetrySettingsCard } from "./TelemetrySettingsCard";
import { useTelemetryStore } from "../../stores/telemetry";
import { useDeveloperModeStore } from "../../stores/developerModeStore";

describe("TelemetrySettingsCard", () => {
  beforeEach(() => {
    localStorage.clear();
    useTelemetryStore.setState({ consent: "UNKNOWN", installIdPreview: null });
    useDeveloperModeStore.setState({ developerMode: false });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders consent switch off by default", () => {
    render(<TelemetrySettingsCard />);
    const toggle = screen.getByRole("switch", { name: "允许匿名使用统计" });
    expect(toggle).not.toBeChecked();
    fireEvent.click(screen.getByTestId("telemetry-privacy-link"));
    expect(screen.getByTestId("telemetry-not-collected")).toBeInTheDocument();
  });

  it("shows privacy expand control", () => {
    render(<TelemetrySettingsCard />);
    expect(screen.getByTestId("telemetry-privacy-link")).toHaveTextContent("查看收集内容");
  });

  it("enables consent when user toggles on", () => {
    render(<TelemetrySettingsCard />);
    fireEvent.click(screen.getByRole("switch", { name: "允许匿名使用统计" }));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("ENABLED");
  });

  it("hides install id unless developer mode", () => {
    render(<TelemetrySettingsCard />);
    expect(screen.queryByTestId("telemetry-install-id")).not.toBeInTheDocument();
    useDeveloperModeStore.setState({ developerMode: true });
    cleanup();
    render(<TelemetrySettingsCard />);
    expect(screen.getByTestId("telemetry-install-id")).toBeInTheDocument();
  });
});
