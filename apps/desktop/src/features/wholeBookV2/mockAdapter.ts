import { parseWholeBookV2 } from "./adapter";
import type { WholeBookAnalysisV2 } from "./contracts";
import analysisFixture from "./fixtures/analysisV2.json";

let cached: WholeBookAnalysisV2 | null = null;

/** Build a parseWholeBookV2-valid mock payload for dev / tests. */
export function buildMockWholeBookAnalysisV2(): WholeBookAnalysisV2 {
  if (!cached) {
    cached = parseWholeBookV2(analysisFixture);
  }
  return cached;
}
