import { describe, expect, it } from "vitest";
import { resolveSceneJourneyGate } from "./resolveSceneJourneyGate";

describe("resolveSceneJourneyGate", () => {
  it("asks to confirm when awaiting", () => {
    const gate = resolveSceneJourneyGate({
      awaitingConfirmation: true,
      confirmedRevisionId: 1,
      journeyStatus: null,
      journeySceneRevisionId: null,
    });
    expect(gate.kind).toBe("need_confirm");
    expect(gate.primaryLabel).toBe("去确认场景");
  });

  it("offers generate when confirmed without journey", () => {
    const gate = resolveSceneJourneyGate({
      awaitingConfirmation: false,
      confirmedRevisionId: 8,
      confirmedSource: "user",
      journeyStatus: null,
      journeySceneRevisionId: null,
    });
    expect(gate.kind).toBe("confirmed_no_journey");
    expect(gate.primaryLabel).toBe("生成阅读旅程");
    expect(gate.title).not.toContain("请先确认");
  });

  it("marks stale journey for old revision", () => {
    const gate = resolveSceneJourneyGate({
      awaitingConfirmation: false,
      confirmedRevisionId: 8,
      journeyStatus: "succeeded",
      journeySceneRevisionId: 1,
    });
    expect(gate.kind).toBe("stale_journey");
  });

  it("does not force confirm when run was awaiting but overview says confirmed user", () => {
    const gate = resolveSceneJourneyGate({
      awaitingConfirmation: false,
      confirmedRevisionId: 8,
      confirmedSource: "user",
      journeyStatus: "succeeded",
      journeySceneRevisionId: 1,
    });
    expect(gate.kind).not.toBe("need_confirm");
  });
});
