import { describe, expect, it } from "vitest";
import {
  hasScaffoldHeuristic,
  isRealProviderV2Result,
  needsReanalysisWarning,
} from "./adapter";
import fixture from "./fixtures/analysisV2.json";

describe("CHG-084 formal V2 result origin gating", () => {
  it("test_failed_new_run_does_not_auto_show_scaffold_as_completed", () => {
    const scaffolded = structuredClone(fixture) as any;
    scaffolded.analysis_metadata.result_origin = "real_provider";
    scaffolded.story.structure_stages[0].title = "阶段1";
    scaffolded.story.structure_stages[0].summary =
      "围绕目标、阻力与选择形成完整阶段";
    expect(hasScaffoldHeuristic(scaffolded)).toBe(true);
    expect(isRealProviderV2Result(scaffolded)).toBe(false);
    expect(needsReanalysisWarning(scaffolded)).toBe(true);
  });

  it("real_provider without scaffold is accepted", () => {
    const real = structuredClone(fixture) as any;
    real.analysis_metadata.result_origin = "real_provider";
    // Ensure fixture stages do not trip scaffold heuristic.
    for (const s of real.story.structure_stages) {
      s.title = `Stage ${s.stage_id}`;
      s.summary = "Concrete stage summary from provider.";
    }
    for (const s of real.suspense.lifecycles) {
      s.question = s.question.replace(/悬念@/g, "open question ");
    }
    expect(isRealProviderV2Result(real)).toBe(true);
    expect(needsReanalysisWarning(real)).toBe(false);
  });
});
