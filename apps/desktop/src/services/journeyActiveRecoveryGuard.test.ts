import { describe, expect, it } from "vitest";
import {
  isJourneyActivelyRunning,
  shouldShowUnifiedRecoveryForJourney,
} from "./journeyActiveRecoveryGuard";

describe("CHG-018 journey active recovery guard", () => {
  it("treats starting/running/queued as active", () => {
    for (const s of [
      "starting",
      "queued",
      "pending",
      "resuming",
      "running",
      "scene_profiles_running",
      "journey_starting",
      "journey_running",
    ]) {
      expect(isJourneyActivelyRunning(s)).toBe(true);
    }
  });

  it("hides recovery while journey page is active", () => {
    expect(
      shouldShowUnifiedRecoveryForJourney({
        uiState: "awaiting_reader_journey_start",
        journeyPageActive: true,
      }),
    ).toBe(false);
  });

  it("hides recovery when journey status is starting even if ui awaiting", () => {
    expect(
      shouldShowUnifiedRecoveryForJourney({
        uiState: "awaiting_reader_journey_start",
        journeyStatus: "starting",
      }),
    ).toBe(false);
  });

  it("hides recovery when plan user_status is running", () => {
    expect(
      shouldShowUnifiedRecoveryForJourney({
        uiState: "partial",
        recoveryUserStatus: "running",
      }),
    ).toBe(false);
  });

  it("still shows recovery for true pause without active journey", () => {
    expect(
      shouldShowUnifiedRecoveryForJourney({
        uiState: "awaiting_budget_adjustment",
        journeyStatus: null,
        recoveryUserStatus: "paused_recoverable",
      }),
    ).toBe(true);
  });
});
