import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { FirstLaunchWizard } from "./FirstLaunchWizard";
import { useTelemetryStore } from "../../stores/telemetry";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

describe("FirstLaunchWizard telemetry opt-in", () => {
  afterEach(() => {
    cleanup();
    localStorage.removeItem("storylens.telemetry.consent");
  });

  beforeEach(() => {
    useTelemetryStore.setState({ consent: "UNKNOWN", installIdPreview: null });
  });

  it("defaults anonymous stats off and sets DISABLED when finishing without opt-in", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.click(screen.getByText("稍后配置"));
    fireEvent.click(screen.getByText("进入空书库"));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("DISABLED");
  });

  it("sets ENABLED when user opts in on step 3", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.click(screen.getByText("稍后配置"));
    fireEvent.click(screen.getByTestId("onboarding-telemetry-opt-in").querySelector("input")!);
    fireEvent.click(screen.getByText("进入空书库"));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("ENABLED");
  });
});
