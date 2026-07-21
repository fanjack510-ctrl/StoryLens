import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  BUILD_APP_VERSION,
  formatAppVersionLabel,
  UNKNOWN_VERSION_LABEL,
} from "./appVersion";
import { useAppVersion } from "./useAppVersion";

function VersionProbe() {
  const version = useAppVersion();
  return <span data-testid="probe">{version}</span>;
}

describe("app version helpers", () => {
  afterEach(() => {
    cleanup();
  });

  it("exposes build-injected version and unknown label", () => {
    expect(BUILD_APP_VERSION).toMatch(/^\d+\.\d+\.\d+/);
    expect(formatAppVersionLabel("")).toBe(UNKNOWN_VERSION_LABEL);
    expect(formatAppVersionLabel("  ")).toBe(UNKNOWN_VERSION_LABEL);
    expect(formatAppVersionLabel(undefined)).toBe("版本未知");
    expect(formatAppVersionLabel("1.2.3")).toBe("1.2.3");
  });

  it("useAppVersion resolves build injection in browser/test runtime", async () => {
    render(<VersionProbe />);
    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent(BUILD_APP_VERSION);
    });
    expect(screen.getByTestId("probe")).not.toHaveTextContent("1.0.0-rc1");
    expect(screen.getByTestId("probe")).not.toHaveTextContent("0.1.0");
  });
});
