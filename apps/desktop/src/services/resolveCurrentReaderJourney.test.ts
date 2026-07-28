import { describe, expect, it } from "vitest";
import {
  journeyElapsedMs,
  preserveJourneyRunInParams,
  resolveCurrentReaderJourney,
} from "./resolveCurrentReaderJourney";

describe("resolveCurrentReaderJourney", () => {
  const candidates = [
    {
      id: 1,
      status: "succeeded",
      scene_revision_id: 1,
      result_status: "superseded",
      started_at: "2026-01-01T00:00:00Z",
    },
    {
      id: 2,
      status: "failed",
      scene_revision_id: 2,
      result_status: "current",
      started_at: "2026-07-28T14:28:27Z",
      retryable: true,
    },
    {
      id: 3,
      status: "queued",
      scene_revision_id: 2,
      result_status: "current",
      created_at: "2026-07-28T15:00:00Z",
    },
  ];

  it("prefers URL explicit journeyRun", () => {
    const resolved = resolveCurrentReaderJourney({
      explicitJourneyRunId: 2,
      confirmedRevisionId: 2,
      candidates,
    });
    expect(resolved.source).toBe("url");
    expect(resolved.journey?.id).toBe(2);
  });

  it("prefers active journey for confirmed revision over failed", () => {
    const resolved = resolveCurrentReaderJourney({
      explicitJourneyRunId: null,
      confirmedRevisionId: 2,
      candidates,
    });
    expect(resolved.source).toBe("active_for_revision");
    expect(resolved.journey?.id).toBe(3);
  });

  it("never selects other revision journeys", () => {
    const resolved = resolveCurrentReaderJourney({
      explicitJourneyRunId: null,
      confirmedRevisionId: 2,
      candidates: [candidates[0]!],
    });
    expect(resolved.journey).toBeNull();
    expect(resolved.source).toBe("none");
  });

  it("does not treat analysis run id as journey", () => {
    const resolved = resolveCurrentReaderJourney({
      explicitJourneyRunId: 1,
      confirmedRevisionId: 2,
      candidates: [candidates[0]!],
    });
    // id=1 is revision 1 superseded — rejected for confirmed 2
    expect(resolved.journey).toBeNull();
    expect(resolved.source).toBe("none");
  });

  it("falls through when URL journey belongs to other revision", () => {
    const resolved = resolveCurrentReaderJourney({
      explicitJourneyRunId: 1,
      confirmedRevisionId: 2,
      candidates,
    });
    expect(resolved.source).toBe("active_for_revision");
    expect(resolved.journey?.id).toBe(3);
  });

  it("preserves journeyRun in URLSearchParams", () => {
    const params = new URLSearchParams("chapter=1&analysisRun=1&view=result");
    preserveJourneyRunInParams(params, 2);
    expect(params.get("journeyRun")).toBe("2");
  });

  it("elapsed uses selected journey started_at not old run", () => {
    const ms = journeyElapsedMs({
      journey: {
        id: 2,
        status: "failed",
        started_at: "2026-07-28T14:28:27Z",
        completed_at: "2026-07-28T14:31:13Z",
      },
    });
    expect(ms).toBeGreaterThan(0);
    expect(ms!).toBeLessThan(5 * 60 * 1000);
  });

  it("selects interrupted/failed for confirmed revision when no active", () => {
    const resolved = resolveCurrentReaderJourney({
      explicitJourneyRunId: null,
      confirmedRevisionId: 2,
      candidates: [
        {
          id: 2,
          status: "failed",
          scene_revision_id: 2,
          result_status: "current",
          started_at: "2026-07-28T14:28:27Z",
        },
      ],
    });
    expect(resolved.source).toBe("failed_for_revision");
    expect(resolved.journey?.id).toBe(2);
  });
});
