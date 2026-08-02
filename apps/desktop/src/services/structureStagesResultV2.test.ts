import { describe, expect, it } from "vitest";
import {
  assertStructureStagesResultV2,
  deriveStructureViewState,
  UnsupportedStructureContractError,
} from "./structureStagesResultV2";
import { adaptStructureStagesV1ToV2 } from "./structureStagesV1Adapter";
import {
  FIXTURE_A_AVAILABLE_MULTI,
  FIXTURE_E_INSUFFICIENT,
  FIXTURE_K_V1_LAB,
  FIXTURE_L_UNSUPPORTED_RAW,
  productEnvelope,
} from "../components/wholeBookFree/structure/fixtures/structureUiFixtures";

describe("structureStagesResultV2", () => {
  it("accepts wire v2", () => {
    const v2 = assertStructureStagesResultV2(FIXTURE_A_AVAILABLE_MULTI);
    expect(v2.stages.length).toBeGreaterThanOrEqual(1);
  });

  it("rejects unsupported contract version", () => {
    expect(() => assertStructureStagesResultV2(FIXTURE_L_UNSUPPORTED_RAW)).toThrow(
      UnsupportedStructureContractError,
    );
  });

  it("maps view states", () => {
    expect(
      deriveStructureViewState({
        runStatus: "running",
        fetchStatus: "idle",
      }),
    ).toBe("loading");
    expect(
      deriveStructureViewState({
        runStatus: "cancelled",
        fetchStatus: "idle",
      }),
    ).toBe("canceled");
    expect(
      deriveStructureViewState({
        runStatus: "completed",
        fetchStatus: "success",
        response: productEnvelope(FIXTURE_E_INSUFFICIENT, {
          empty_reason: "INSUFFICIENT_TEXT_VOLUME",
        }),
      }),
    ).toBe("insufficient");
    expect(
      deriveStructureViewState({
        runStatus: "completed",
        fetchStatus: "error",
        httpStatus: 404,
        errorCode: "STRUCTURE_RESULT_ABSENT",
      }),
    ).toBe("absent");
  });

  it("adapts V1 Lab DTO", () => {
    const adapted = adaptStructureStagesV1ToV2(FIXTURE_K_V1_LAB);
    expect(adapted.contract_version).toBe("v2");
    expect(adapted.limitations).toContain("V1_ADAPTER_ONLY");
    expect(adapted.stages).toHaveLength(2);
  });
});
