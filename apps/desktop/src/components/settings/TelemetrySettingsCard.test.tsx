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

  // 原来这里是「开发者模式下才显示安装 ID」。开发者模式已删，那条断言的后半段
  // ——「切到开发者模式后它应该出现」——现在没有任何路径能满足。留下的是前半段：
  // 安装 ID 不出现在任何界面上。
  it("安装 ID 不出现在界面上", () => {
    render(<TelemetrySettingsCard />);
    expect(screen.queryByTestId("telemetry-install-id")).not.toBeInTheDocument();
  });
});
