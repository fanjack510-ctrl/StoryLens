import { describe, expect, it } from "vitest";
import {
  assertChapterFunctionsResultV2,
  CANONICAL_FUNCTION_LABELS,
  CHAPTER_FUNCTIONS_DEFAULT_LIMIT,
  CHAPTER_FUNCTIONS_MAX_LIMIT,
  clampChapterFunctionsLimit,
  deriveChapterFunctionsViewState,
  FUNCTION_LABEL_DISPLAY_ZH,
  functionLabelDisplayZh,
  resolveEvidenceIdForCitation,
  UnsupportedChapterFunctionsContractError,
} from "./chapterFunctionsResultV2";
import {
  CHAPTER_FUNCTIONS_UI_FIXTURES,
  FIXTURE_A_AVAILABLE,
  FIXTURE_C_PRIMARY_NULL,
  FIXTURE_F_INSUFFICIENT,
  FIXTURE_LAB_V1_ADAPTER,
  productEnvelope,
} from "../components/wholeBookFree/chapterFunctions/fixtures/chapterFunctionsUiFixtures";

describe("chapterFunctionsResultV2", () => {
  it("accepts wire v2 and rejects unsupported versions", () => {
    const v2 = assertChapterFunctionsResultV2(FIXTURE_A_AVAILABLE);
    expect(v2.chapters.length).toBeGreaterThanOrEqual(1);
    expect(() =>
      assertChapterFunctionsResultV2({
        contract_version: "v1",
        evidence_contract_version: "v1",
        coverage_scope: "full_selected_range",
        chapters: [],
      }),
    ).toThrow(UnsupportedChapterFunctionsContractError);
  });

  it("maps freeze Chinese labels (not Prompt alternate copy)", () => {
    expect(functionLabelDisplayZh("setup")).toBe("开篇/建立");
    expect(functionLabelDisplayZh("escalation")).toBe("冲突升级");
    expect(functionLabelDisplayZh("resolution")).toBe("收束");
    expect(functionLabelDisplayZh("side_story")).toBe("支线章");
    expect(functionLabelDisplayZh("empty")).toBe("空章/填充");
    expect(functionLabelDisplayZh("non_mainline")).toBe("非主线");
    expect(functionLabelDisplayZh("unknown")).toBe("未判定");
    expect(FUNCTION_LABEL_DISPLAY_ZH.setup).not.toBe("建立与铺垫");
    expect(CANONICAL_FUNCTION_LABELS).toHaveLength(10);
  });

  it("clamps pagination limits", () => {
    expect(CHAPTER_FUNCTIONS_DEFAULT_LIMIT).toBe(50);
    expect(CHAPTER_FUNCTIONS_MAX_LIMIT).toBe(200);
    expect(clampChapterFunctionsLimit(999)).toBe(200);
    expect(clampChapterFunctionsLimit(undefined)).toBe(50);
  });

  it("resolves citation evidence bindings without evidence_map wrapper", () => {
    const eid = resolveEvidenceIdForCitation("CIT-TEST0001-0001", [
      { citation_id: "CIT-TEST0001-0001", evidence_id: 601 },
    ]);
    expect(eid).toBe(601);
    expect(resolveEvidenceIdForCitation("missing", [])).toBeNull();
  });

  it("derives view states including partial and insufficient", () => {
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "running",
        fetchStatus: "idle",
      }),
    ).toBe("loading");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "cancelled",
        fetchStatus: "idle",
      }),
    ).toBe("canceled");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "success",
        response: CHAPTER_FUNCTIONS_UI_FIXTURES.F_insufficient,
      }),
    ).toBe("insufficient");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "success",
        response: CHAPTER_FUNCTIONS_UI_FIXTURES.E_partial,
      }),
    ).toBe("partial");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "success",
        response: CHAPTER_FUNCTIONS_UI_FIXTURES.A_available,
      }),
    ).toBe("available");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "error",
        httpStatus: 404,
        errorCode: "CHAPTER_FUNCTIONS_RESULT_ABSENT",
      }),
    ).toBe("absent");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "error",
        errorCode: "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED",
      }),
    ).toBe("unsupported_contract");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "success",
        response: CHAPTER_FUNCTIONS_UI_FIXTURES.G_failed,
      }),
    ).toBe("failed");
    expect(
      deriveChapterFunctionsViewState({
        runStatus: "completed",
        fetchStatus: "success",
        response: CHAPTER_FUNCTIONS_UI_FIXTURES.I_conflict,
      }),
    ).toBe("conflict");
  });

  it("allows primary=null and keeps Lab V1 adapter namespaced separately", () => {
    const item = FIXTURE_C_PRIMARY_NULL.chapters[0];
    expect(item.primary_function).toBeNull();
    expect(item.secondary_functions.length).toBeGreaterThan(0);
    expect(FIXTURE_LAB_V1_ADAPTER.adapted_from).toBe("ChapterFunctionsResultV2");
    expect(FIXTURE_LAB_V1_ADAPTER.contract_version).toBe("v1");
    const env = productEnvelope(FIXTURE_F_INSUFFICIENT);
    expect(env.chapter_functions?.chapters).toEqual([]);
  });
});
