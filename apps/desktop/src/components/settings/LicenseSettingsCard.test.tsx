import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { LicenseSettingsCard } from "./LicenseSettingsCard";
import {
  createLicenseService,
  createMemoryLicenseStorage,
  MOCK_ACTIVATION_CODES,
  setLicenseServiceForTests,
} from "../../services/license";
import { useLicenseStore } from "../../stores/license";

describe("LicenseSettingsCard", () => {
  beforeEach(() => {
    const service = createLicenseService({
      storage: createMemoryLicenseStorage(),
      allowMockInTests: true,
    });
    setLicenseServiceForTests(service);
    useLicenseStore.setState({
      status: "FREE",
      editionLabel: "免费版",
      license: null,
      usingMockService: true,
      commerceComingSoon: true,
      hydrated: false,
      busy: false,
      message: "",
      error: "",
    });
  });

  afterEach(() => {
    cleanup();
    setLicenseServiceForTests(null);
  });

  it("renders free edition, coming soon, and VIP feature list", async () => {
    render(<LicenseSettingsCard />);
    await waitFor(() => {
      expect(screen.getByTestId("license-edition")).toHaveTextContent("免费版");
    });
    expect(screen.getByTestId("license-coming-soon")).toHaveTextContent("即将开放");
    expect(screen.queryByText(/¥|￥|\$\d/)).toBeNull();
    expect(screen.getByTestId("license-vip-features")).toHaveTextContent("批量分析");
  });

  it("activates via mock code in development", async () => {
    render(<LicenseSettingsCard />);
    await waitFor(() => expect(screen.getByTestId("license-code-input")).toBeEnabled());
    fireEvent.change(screen.getByTestId("license-code-input"), {
      target: { value: MOCK_ACTIVATION_CODES.ACTIVE },
    });
    fireEvent.click(screen.getByTestId("license-activate-button"));
    await waitFor(() => {
      expect(screen.getByTestId("license-status")).toHaveTextContent("VIP 已激活");
    });
  });

  it("deactivates back to free", async () => {
    render(<LicenseSettingsCard />);
    await waitFor(() => expect(screen.getByTestId("license-code-input")).toBeEnabled());
    fireEvent.change(screen.getByTestId("license-code-input"), {
      target: { value: MOCK_ACTIVATION_CODES.ACTIVE },
    });
    fireEvent.click(screen.getByTestId("license-activate-button"));
    await waitFor(() => {
      expect(screen.getByTestId("license-deactivate-button")).toBeEnabled();
    });
    fireEvent.click(screen.getByTestId("license-deactivate-button"));
    await waitFor(() => {
      expect(screen.getByTestId("license-status")).toHaveTextContent("免费版");
    });
  });
});
