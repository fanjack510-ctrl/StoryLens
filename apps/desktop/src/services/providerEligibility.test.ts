import { describe, expect, it } from "vitest";
import { manualBoundaryEligibility, PROVIDER_ELIGIBILITY_MISSING } from "./providerEligibility";

const provider = (value: unknown, blockers: unknown) => ({
  manual_boundary_candidate_eligible: value, manual_selection_blockers: blockers,
} as any);

describe("manualBoundaryEligibility", () => {
  it("only accepts an explicit true with a blocker list", () => {
    expect(manualBoundaryEligibility(provider(true, [])).status).toBe("eligible");
  });
  it("reports explicit false with blockers as blocked", () => {
    expect(manualBoundaryEligibility(provider(false, ["provider_disconnected"]))).toEqual({
      status: "blocked", blockers: ["provider_disconnected"],
    });
  });
  it.each([[undefined, []], [null, []], ["true", []], [false, []], [true, null]])(
    "treats missing or malformed contract data as unknown",
    (value, blockers) => expect(manualBoundaryEligibility(provider(value, blockers))).toEqual({
      status: "unknown", blockers: [PROVIDER_ELIGIBILITY_MISSING],
    }),
  );
});
