/**
 * TEST-ONLY fixtures for WB-2.1 structure stages Desktop UI (CHG-20260801-035).
 * Explicitly labelled as test data — must not write formal databases.
 */
import type {
  StructureProductResponse,
  StructureStagesResultV2,
} from "../../../../services/structureStagesResultV2";
import type { StructureStagesResultDto } from "../../../../features/wholeBook/contracts/moduleResults";

export const STRUCTURE_UI_FIXTURE_BANNER =
  "TEST DATA · WB-2.1 structure UI fixtures · not formal analysis results";

function claim(
  value: string,
  status: "observed" | "inferred",
  citationIds: string[],
  confidence = 0.8,
) {
  return { value, status, citation_ids: citationIds, confidence };
}

function boundary(citationIds: string[], value: string | null = null) {
  return { citation_ids: citationIds, value, note: null, status: null, confidence: null };
}

/** A — available, multi-stage */
export const FIXTURE_A_AVAILABLE_MULTI: StructureStagesResultV2 = {
  contract_version: "v2",
  evidence_contract_version: "v2",
  coverage_scope: "full_selected_range",
  analysis_confidence: 0.86,
  overall_confidence: 0.86,
  limitations: [],
  context_capabilities: {
    can_identify_local_stages: true,
    can_identify_span_stages: true,
    can_identify_turning_points: true,
    is_full_book_coverage: true,
  },
  stages: [
    {
      local_stage_ref: "S1",
      order_index: 0,
      stage_type: "setup",
      title: "开局承压",
      summary: claim("主角进入陌生环境并接受试炼。", "observed", ["CIT-TEST0001-0001"]),
      start_boundary: boundary(["CIT-TEST0001-0001"], "ch1"),
      end_boundary: boundary(["CIT-TEST0001-0002"], "ch3"),
      supporting_citation_ids: ["CIT-TEST0001-0001"],
      related_turning_point_refs: ["TP1"],
      narrative_function: "建立压力与目标",
      confidence: 0.84,
      chapter_range: [1, 3],
    },
    {
      local_stage_ref: "S2",
      order_index: 1,
      stage_type: "rising",
      title: "对抗升级",
      summary: claim("冲突扩大，盟友与对手同时出现。", "observed", ["CIT-TEST0001-0003"]),
      start_boundary: boundary(["CIT-TEST0001-0003"], "ch4"),
      end_boundary: boundary(["CIT-TEST0001-0004"], "ch8"),
      supporting_citation_ids: [],
      related_turning_point_refs: ["TP1"],
      narrative_function: "抬升代价",
      confidence: 0.8,
      chapter_range: [4, 8],
    },
    {
      local_stage_ref: "S3",
      order_index: 2,
      stage_type: "climax",
      title: "决断时刻",
      summary: claim("主角做出不可逆选择并承担后果。", "inferred", ["CIT-TEST0001-0005"]),
      start_boundary: boundary(["CIT-TEST0001-0005"], "ch9"),
      end_boundary: boundary(["CIT-TEST0001-0006"], "ch12"),
      supporting_citation_ids: [],
      related_turning_point_refs: [],
      narrative_function: "收束主线",
      confidence: 0.78,
      chapter_range: [9, 12],
    },
  ],
  turning_points: [
    {
      local_turning_point_ref: "TP1",
      order_index: 0,
      turning_point_type: "reveal",
      title: "身份暴露",
      description: claim("关键秘密被揭开，局势转向。", "observed", ["CIT-TEST0001-0003"]),
      citation_ids: ["CIT-TEST0001-0003"],
      related_stage_refs: ["S1", "S2"],
      confidence: 0.77,
      chapter_id: 4,
    },
  ],
};

/** B — non-three-act labels (4 stages, no 幕 labels) */
export const FIXTURE_B_NON_THREE_ACT: StructureStagesResultV2 = {
  ...FIXTURE_A_AVAILABLE_MULTI,
  stages: [
    {
      local_stage_ref: "S1",
      order_index: 0,
      stage_type: "arrival",
      title: "抵达",
      summary: claim("进入新场域。", "observed", ["CIT-TEST0001-0001"]),
      start_boundary: boundary(["CIT-TEST0001-0001"]),
      end_boundary: boundary(["CIT-TEST0001-0001"]),
      chapter_range: [1, 2],
      confidence: 0.7,
    },
    {
      local_stage_ref: "S2",
      order_index: 1,
      stage_type: "probe",
      title: "试探",
      summary: claim("试探规则边界。", "observed", ["CIT-TEST0001-0002"]),
      start_boundary: boundary(["CIT-TEST0001-0002"]),
      end_boundary: boundary(["CIT-TEST0001-0002"]),
      chapter_range: [3, 5],
      confidence: 0.7,
    },
    {
      local_stage_ref: "S3",
      order_index: 2,
      stage_type: "breach",
      title: "破局",
      summary: claim("打破既有平衡。", "observed", ["CIT-TEST0001-0003"]),
      start_boundary: boundary(["CIT-TEST0001-0003"]),
      end_boundary: boundary(["CIT-TEST0001-0003"]),
      chapter_range: [6, 9],
      confidence: 0.72,
    },
    {
      local_stage_ref: "S4",
      order_index: 3,
      stage_type: "aftermath",
      title: "余波",
      summary: claim("处理破局后果。", "inferred", ["CIT-TEST0001-0004"]),
      start_boundary: boundary(["CIT-TEST0001-0004"]),
      end_boundary: boundary(["CIT-TEST0001-0004"]),
      chapter_range: [10, 12],
      confidence: 0.69,
    },
  ],
  turning_points: [],
};

/** C — variable stage count (single stage) */
export const FIXTURE_C_VARIABLE_COUNT: StructureStagesResultV2 = {
  contract_version: "v2",
  evidence_contract_version: "v2",
  coverage_scope: "local",
  analysis_confidence: 0.61,
  limitations: ["RESOURCE_LIMIT_TRUNCATED"],
  context_capabilities: { can_identify_local_stages: true },
  stages: [
    {
      local_stage_ref: "S1",
      order_index: 0,
      stage_type: "local",
      title: "局部阶段",
      summary: claim("仅识别出一段局部推进。", "observed", ["CIT-TEST0001-0001"]),
      start_boundary: boundary(["CIT-TEST0001-0001"]),
      end_boundary: boundary(["CIT-TEST0001-0002"]),
      chapter_range: [2, 2],
      confidence: 0.61,
    },
  ],
  turning_points: [],
};

/** D — turning_points empty with valid stages */
export const FIXTURE_D_TP_EMPTY: StructureStagesResultV2 = {
  ...FIXTURE_A_AVAILABLE_MULTI,
  turning_points: [],
  limitations: ["TURNING_POINTS_NOT_RESOLVED"],
};

/** E — insufficient empty */
export const FIXTURE_E_INSUFFICIENT: StructureStagesResultV2 = {
  contract_version: "v2",
  evidence_contract_version: "v2",
  coverage_scope: "insufficient",
  analysis_confidence: null,
  overall_confidence: null,
  limitations: ["INSUFFICIENT_TEXT_VOLUME", "can_identify_local_stages=false"],
  context_capabilities: {
    can_identify_local_stages: false,
    can_identify_span_stages: false,
    can_identify_turning_points: false,
  },
  stages: [],
  turning_points: [],
};

export const BINDINGS_A: StructureProductResponse["citation_evidence_bindings"] = [
  { citation_id: "CIT-TEST0001-0001", evidence_id: 501 },
  { citation_id: "CIT-TEST0001-0002", evidence_id: 502 },
  { citation_id: "CIT-TEST0001-0003", evidence_id: 503 },
  { citation_id: "CIT-TEST0001-0004", evidence_id: 504 },
  { citation_id: "CIT-TEST0001-0005", evidence_id: 505 },
  { citation_id: "CIT-TEST0001-0006", evidence_id: 506 },
];

export function productEnvelope(
  structure: StructureStagesResultV2 | null,
  overrides: Partial<StructureProductResponse> = {},
): StructureProductResponse {
  return {
    result_status: "completed",
    coverage_scope: structure?.coverage_scope ?? null,
    structure,
    failure_code: null,
    empty_reason: null,
    failure_message_safe: null,
    source_revision: {
      run_id: 42,
      snapshot_id: 11,
      snapshot_revision: "rev-test-1",
    },
    conflict: null,
    citation_evidence_bindings: structure ? BINDINGS_A : [],
    ...overrides,
  };
}

/** E envelope */
export const FIXTURE_E_PRODUCT = productEnvelope(FIXTURE_E_INSUFFICIENT, {
  empty_reason: "INSUFFICIENT_TEXT_VOLUME",
});

/** F — failed */
export const FIXTURE_F_FAILED: StructureProductResponse = {
  result_status: "failed",
  coverage_scope: null,
  structure: null,
  failure_code: "STRUCTURE_EMPTY_RESULT_AFTER_REPAIR",
  empty_reason: "PROVIDER_OUTPUT_UNRECOVERABLE",
  failure_message_safe: "结构阶段结果未能通过合同校验。",
  source_revision: { run_id: 42, snapshot_id: 11, snapshot_revision: "rev-test-1" },
  citation_evidence_bindings: [],
};

/** G — canceled */
export const FIXTURE_G_CANCELED: StructureProductResponse = {
  result_status: "canceled",
  coverage_scope: null,
  structure: null,
  failure_code: null,
  empty_reason: null,
  failure_message_safe: "任务已取消。",
  source_revision: { run_id: 42, snapshot_id: 11 },
  citation_evidence_bindings: [],
};

/** H — conflict */
export const FIXTURE_H_CONFLICT: StructureProductResponse = {
  result_status: "conflict",
  coverage_scope: "partial_span",
  structure: FIXTURE_A_AVAILABLE_MULTI,
  failure_code: null,
  empty_reason: null,
  source_revision: { run_id: 42, snapshot_id: 11, snapshot_revision: "rev-test-1" },
  conflict: {
    versions: [
      { version_id: "v-confirmed", label: "已确认版本", state: "confirmed", created_at: "2026-07-01T00:00:00Z" },
      { version_id: "v-candidate", label: "新候选版本", state: "candidate", created_at: "2026-08-01T00:00:00Z" },
    ],
    current_pointer: "v-confirmed",
  },
  citation_evidence_bindings: BINDINGS_A,
};

/** L — unsupported contract version payload (raw) */
export const FIXTURE_L_UNSUPPORTED_RAW = {
  contract_version: "v1",
  evidence_contract_version: "v1",
  coverage_scope: "partial_span",
  stages: [],
  turning_points: [],
};

/** K — V1 Lab DTO for adapter tests */
export const FIXTURE_K_V1_LAB: StructureStagesResultDto = {
  stages: [
    {
      stage_id: "act1",
      label: "历史阶段甲",
      chapter_range: [1, 4],
      narrative_function: "铺垫",
      order: 0,
    },
    {
      stage_id: "act2",
      label: "历史阶段乙",
      chapter_range: [5, 10],
      narrative_function: "推进",
      order: 1,
    },
  ],
  turning_points: [
    {
      turning_point_id: "tp-old",
      label: "旧转折",
      chapter_id: 5,
      summary: "V1 转折摘要",
    },
  ],
  act_or_phase_labels: ["甲", "乙"],
  chapter_ranges: [
    [1, 4],
    [5, 10],
  ],
  narrative_function: "legacy",
  evidence_refs: [{ evidence_id: 1, evidence_role: "support" }],
  confidence: 0.55,
};

export const STRUCTURE_UI_FIXTURES = {
  A_available_multi: productEnvelope(FIXTURE_A_AVAILABLE_MULTI),
  B_non_three_act: productEnvelope(FIXTURE_B_NON_THREE_ACT),
  C_variable_count: productEnvelope(FIXTURE_C_VARIABLE_COUNT),
  D_tp_empty: productEnvelope(FIXTURE_D_TP_EMPTY),
  E_insufficient: FIXTURE_E_PRODUCT,
  F_failed: FIXTURE_F_FAILED,
  G_canceled: FIXTURE_G_CANCELED,
  H_conflict: FIXTURE_H_CONFLICT,
  K_v1_lab: FIXTURE_K_V1_LAB,
  L_unsupported_raw: FIXTURE_L_UNSUPPORTED_RAW,
} as const;
