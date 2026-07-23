import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { assertPreflightGuard } from "../../contracts/guards";
import { FIXTURE_PREFLIGHT_ENRICHED } from "../fixtures/preflightFixtures";
import { WholeBookRunUxLabPage } from "../pages/WholeBookRunUxLabPage";
import {
  RUN_CREATE_ENABLED_IN_CLIENT,
  WHOLE_BOOK_RUN_CREATE_PATH,
} from "../preflightClient";
import { mapPhase1cPreflightToPageModel } from "../preflightMapper";
import { FIXTURE_PHASE1C_PREFLIGHT_RESPONSE } from "../fixtures/preflightFixtures";

afterEach(() => {
  cleanup();
});

describe("DTO guards, theme, a11y, no real start", () => {
  it("assertPreflightGuard passes on fixture and rejects force start", () => {
    assertPreflightGuard(FIXTURE_PREFLIGHT_ENRICHED);
    expect(FIXTURE_PREFLIGHT_ENRICHED.force_start_allowed).toBe(false);
    expect(() =>
      assertPreflightGuard({
        ...FIXTURE_PREFLIGHT_ENRICHED,
        force_start_allowed: true as false,
      }),
    ).toThrow(/force_start_allowed/);
  });

  it("mapper output always fails closed on create gate", () => {
    const mapped = mapPhase1cPreflightToPageModel(
      FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
    );
    assertPreflightGuard(mapped.model);
    expect(mapped.model.run_creation_enabled).toBe(false);
  });

  it("lab page supports light/dark theme and keyboard controls", () => {
    render(<WholeBookRunUxLabPage useFixtures />);
    const root = screen.getByTestId("whole-book-run-ux-lab");
    expect(root).toHaveAttribute("data-theme", "light");
    const toggle = screen.getByTestId("theme-toggle");
    toggle.focus();
    expect(document.activeElement).toBe(toggle);
    fireEvent.click(toggle);
    expect(root).toHaveAttribute("data-theme", "dark");
    fireEvent.click(screen.getByTestId("tab-progress"));
    expect(screen.getByTestId("whole-book-run-progress-view")).toBeInTheDocument();
  });

  it("proves no real start wiring in client constants", () => {
    expect(RUN_CREATE_ENABLED_IN_CLIENT).toBe(false);
    expect(WHOLE_BOOK_RUN_CREATE_PATH).toBe(
      "/api/v1/books/{book_id}/whole-book-runs",
    );
    render(<WholeBookRunUxLabPage useFixtures />);
    expect(screen.getByTestId("start-whole-book-analysis")).toBeDisabled();
    expect(screen.queryByText("强制启动")).not.toBeInTheDocument();
  });

  it("status is not color-only — text status present", () => {
    render(<WholeBookRunUxLabPage useFixtures initialRunFixture="failed" />);
    fireEvent.click(screen.getByTestId("tab-progress"));
    expect(screen.getByTestId("run-status-text")).toHaveTextContent("失败");
    expect(screen.getByTestId("run-status-text").textContent?.length).toBeGreaterThan(
      2,
    );
  });
});
