import type { NarrativePatternMapDto } from "../contracts/patternMap.draft";
import { validateNarrativePatternMapDto } from "../contracts/patternMap.guards";
import rawMock from "../mocks/pattern-map.mock.json";

export function loadPatternMapMock(): NarrativePatternMapDto {
  const result = validateNarrativePatternMapDto(rawMock);
  if (!result.ok) {
    const detail = result.issues.map((i) => `${i.path}: ${i.message}`).join("; ");
    throw new Error(`pattern-map.mock.json failed schema validation: ${detail}`);
  }
  return result.data;
}

export { rawMock as patternMapMockJson };
