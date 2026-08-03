/**
 * TEST-ONLY fixtures for WB-2.2 chapter functions Desktop UI (CHG-20260803-041).
 * Explicitly labelled as test data — must not write formal databases.
 * Label Chinese display follows FUNCTION_LABEL_POLICY_FREEZE.md.
 */
import type {
  ChapterFunctionItemV2,
  ChapterFunctionsProductResponse,
  ChapterFunctionsResultV2,
  LabChapterFunctionsResultV1,
} from "../../../../services/chapterFunctionsResultV2";

export const CHAPTER_FUNCTIONS_UI_FIXTURE_BANNER =
  "TEST DATA · WB-2.2 chapter functions UI fixtures · not formal analysis results";

function encodeCursor(chapterOrder: number): string {
  const raw = JSON.stringify({ chapter_order: chapterOrder });
  // Vitest/Node + browser-safe base64url
  const bytes = new TextEncoder().encode(raw);
  let bin = "";
  bytes.forEach((b) => {
    bin += String.fromCharCode(b);
  });
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function claim(
  value: string,
  status: "observed" | "inferred" | "not_observed",
  citationIds: string[],
  confidence = 0.8,
) {
  return { value, status, citation_ids: citationIds, confidence };
}

function chapter(
  partial: Partial<ChapterFunctionItemV2> &
    Pick<ChapterFunctionItemV2, "chapter_id" | "chapter_order" | "primary_function">,
): ChapterFunctionItemV2 {
  const cid = `CIT-TEST0001-${String(partial.chapter_order).padStart(4, "0")}`;
  return {
    secondary_functions: [],
    observed_summary: claim(`第 ${partial.chapter_order} 章观察摘要`, "observed", [cid]),
    inferred_effect: null,
    confidence: 0.8,
    supporting_citation_ids: [cid],
    limitations: [],
    chapter_title: `第${partial.chapter_order}章`,
    ...partial,
  };
}

const BINDINGS = [
  { citation_id: "CIT-TEST0001-0001", evidence_id: 601 },
  { citation_id: "CIT-TEST0001-0002", evidence_id: 602 },
  { citation_id: "CIT-TEST0001-0003", evidence_id: 603 },
  { citation_id: "CIT-TEST0001-0004", evidence_id: 604 },
];

/** A — available */
export const FIXTURE_A_AVAILABLE: ChapterFunctionsResultV2 = {
  contract_version: "v2",
  evidence_contract_version: "v2",
  coverage_scope: "full_selected_range",
  analysis_confidence: 0.84,
  overall_confidence: 0.84,
  limitations: [],
  context_capabilities: {
    structure_context_used: true,
    structure_context_status: "available",
  },
  chapters: [
    chapter({
      chapter_id: 1,
      chapter_order: 1,
      primary_function: "setup",
      secondary_functions: ["transition"],
      observed_summary: claim("开篇建立人物与压力。", "observed", ["CIT-TEST0001-0001"]),
      supporting_citation_ids: ["CIT-TEST0001-0001"],
    }),
    chapter({
      chapter_id: 2,
      chapter_order: 2,
      primary_function: "escalation",
      secondary_functions: [],
      observed_summary: claim("冲突开始升级。", "observed", ["CIT-TEST0001-0002"]),
      supporting_citation_ids: ["CIT-TEST0001-0002"],
    }),
  ],
};

/** B — primary + secondary */
export const FIXTURE_B_PRIMARY_SECONDARY: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  chapters: [
    chapter({
      chapter_id: 1,
      chapter_order: 1,
      primary_function: "climax",
      secondary_functions: ["flashback", "side_story"],
      observed_summary: claim("高潮并穿插回溯。", "observed", ["CIT-TEST0001-0001"]),
      inferred_effect: claim("主线代价锁定。", "inferred", ["CIT-TEST0001-0001"], 0.72),
      supporting_citation_ids: ["CIT-TEST0001-0001"],
    }),
  ],
};

/** C — primary=null */
export const FIXTURE_C_PRIMARY_NULL: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  chapters: [
    chapter({
      chapter_id: 3,
      chapter_order: 3,
      primary_function: null,
      secondary_functions: ["transition"],
      observed_summary: claim("辅助过渡可见，主功能未达可靠阈值。", "observed", [
        "CIT-TEST0001-0003",
      ]),
      supporting_citation_ids: ["CIT-TEST0001-0003"],
    }),
  ],
};

/** D — secondary=[] */
export const FIXTURE_D_SECONDARY_EMPTY: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  chapters: [
    chapter({
      chapter_id: 4,
      chapter_order: 4,
      primary_function: "resolution",
      secondary_functions: [],
      observed_summary: claim("收束主线冲突。", "observed", ["CIT-TEST0001-0004"]),
      supporting_citation_ids: ["CIT-TEST0001-0004"],
    }),
  ],
};

/** E — partial */
export const FIXTURE_E_PARTIAL: ChapterFunctionsResultV2 = {
  contract_version: "v2",
  evidence_contract_version: "v2",
  coverage_scope: "partial_span",
  analysis_confidence: 0.7,
  overall_confidence: 0.7,
  limitations: ["PARTIAL_BATCH_INCOMPLETE", "未完成章节仍在后续批次"],
  context_capabilities: { structure_context_status: "available" },
  chapters: [
    chapter({
      chapter_id: 1,
      chapter_order: 1,
      primary_function: "setup",
      supporting_citation_ids: ["CIT-TEST0001-0001"],
      observed_summary: claim("部分批次已完成。", "observed", ["CIT-TEST0001-0001"]),
    }),
  ],
};

/** F — insufficient */
export const FIXTURE_F_INSUFFICIENT: ChapterFunctionsResultV2 = {
  contract_version: "v2",
  evidence_contract_version: "v2",
  coverage_scope: "insufficient",
  chapters: [],
  limitations: ["INSUFFICIENT_TEXT_VOLUME"],
  empty_reason: "INSUFFICIENT_TEXT_VOLUME",
  context_capabilities: { structure_context_status: "absent" },
};

/** U — empty label */
export const FIXTURE_U_EMPTY_LABEL: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  chapters: [
    chapter({
      chapter_id: 10,
      chapter_order: 10,
      primary_function: "empty",
      secondary_functions: [],
      observed_summary: claim("本章无明显叙事推进。", "observed", ["CIT-TEST0001-0001"]),
      supporting_citation_ids: ["CIT-TEST0001-0001"],
    }),
  ],
};

/** V — non_mainline */
export const FIXTURE_V_NON_MAINLINE: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  chapters: [
    chapter({
      chapter_id: 11,
      chapter_order: 11,
      primary_function: "non_mainline",
      secondary_functions: [],
      observed_summary: claim("支线闲笔。", "observed", ["CIT-TEST0001-0002"]),
      supporting_citation_ids: ["CIT-TEST0001-0002"],
    }),
  ],
};

/** W — unknown */
export const FIXTURE_W_UNKNOWN: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  chapters: [
    chapter({
      chapter_id: 12,
      chapter_order: 12,
      primary_function: "unknown",
      secondary_functions: [],
      observed_summary: claim("证据不足以判定。", "inferred", ["CIT-TEST0001-0003"], 0.4),
      supporting_citation_ids: ["CIT-TEST0001-0003"],
      confidence: 0.4,
    }),
  ],
};

/** R — WB-2.1 context available */
export const FIXTURE_R_WB21_CONTEXT_AVAILABLE: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  context_capabilities: {
    structure_context_used: true,
    structure_context_status: "available",
    can_use_structure_derived_context: true,
  },
};

/** S — WB-2.1 context absent */
export const FIXTURE_S_WB21_CONTEXT_ABSENT: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  context_capabilities: {
    structure_context_used: false,
    structure_context_status: "absent",
  },
};

/** T — WB-2.1 context insufficient (must NOT fail CF) */
export const FIXTURE_T_WB21_CONTEXT_INSUFFICIENT: ChapterFunctionsResultV2 = {
  ...FIXTURE_A_AVAILABLE,
  context_capabilities: {
    structure_context_used: false,
    structure_context_status: "insufficient",
  },
  limitations: ["STRUCTURE_CONTEXT_INSUFFICIENT_OPTIONAL"],
};

export function productEnvelope(
  cf: ChapterFunctionsResultV2 | null,
  overrides: Partial<ChapterFunctionsProductResponse> = {},
): ChapterFunctionsProductResponse {
  const items = overrides.items ?? cf?.chapters ?? [];
  return {
    result_status: "completed",
    contract_version: "v2",
    schema_version: "2.0.0",
    coverage_scope: cf?.coverage_scope ?? null,
    chapter_functions: cf,
    items,
    next_cursor: null,
    total_chapters: items.length,
    failure_code: null,
    empty_reason: cf?.empty_reason ?? null,
    source_revision: { run_id: 42, snapshot_id: 11, snapshot_revision: "rev-cf-ui", book_id: 1 },
    evidence_references: items.flatMap((c) => c.supporting_citation_ids ?? []),
    fixture_test_data: true,
    citation_evidence_bindings: BINDINGS,
    analyzed_chapter_count: items.length,
    unfinished_chapter_count: 0,
    ...overrides,
  };
}

/** Long-book page 1 of 1299 (limit 50). */
export function longBookPage(
  pageIndex: number,
  limit = 50,
  total = 1299,
): ChapterFunctionsProductResponse {
  const startOrder = pageIndex * limit + 1;
  const endOrder = Math.min(startOrder + limit - 1, total);
  const items: ChapterFunctionItemV2[] = [];
  for (let order = startOrder; order <= endOrder; order++) {
    const cid = `CIT-LONG-${String(order).padStart(4, "0")}`;
    items.push(
      chapter({
        chapter_id: order,
        chapter_order: order,
        primary_function: order % 7 === 0 ? "climax" : "setup",
        secondary_functions: order % 5 === 0 ? ["transition"] : [],
        observed_summary: claim(`长书第 ${order} 章`, "observed", [cid]),
        supporting_citation_ids: [cid],
        chapter_title: `第${order}章`,
      }),
    );
  }
  const hasMore = endOrder < total;
  const nextCursor = hasMore ? encodeCursor(endOrder) : null;
  const cf: ChapterFunctionsResultV2 = {
    contract_version: "v2",
    evidence_contract_version: "v2",
    coverage_scope: "full_selected_range",
    chapters: items,
    analysis_confidence: 0.75,
    overall_confidence: 0.75,
    limitations: ["LONG_BOOK_PAGINATED_FIXTURE"],
    context_capabilities: { structure_context_status: "absent" },
  };
  return productEnvelope(cf, {
    items,
    next_cursor: nextCursor,
    total_chapters: total,
    analyzed_chapter_count: total,
  });
}

export const CHAPTER_FUNCTIONS_UI_FIXTURES = {
  A_available: productEnvelope(FIXTURE_A_AVAILABLE),
  B_primary_secondary: productEnvelope(FIXTURE_B_PRIMARY_SECONDARY),
  C_primary_null: productEnvelope(FIXTURE_C_PRIMARY_NULL),
  D_secondary_empty: productEnvelope(FIXTURE_D_SECONDARY_EMPTY),
  E_partial: productEnvelope(FIXTURE_E_PARTIAL, {
    unfinished_chapter_count: 40,
    analyzed_chapter_count: 1,
    total_chapters: 41,
    product_result_status: "partial",
  }),
  F_insufficient: productEnvelope(FIXTURE_F_INSUFFICIENT, {
    result_status: "completed",
    product_result_status: "insufficient",
    coverage_scope: "insufficient",
    items: [],
    total_chapters: 0,
  }),
  G_failed: {
    result_status: "failed",
    contract_version: "v2",
    schema_version: "2.0.0",
    coverage_scope: null,
    chapter_functions: null,
    items: [],
    next_cursor: null,
    total_chapters: 0,
    failure_code: "CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR",
    failure_message_safe: "章节功能分析失败（测试夹具）",
    source_revision: { run_id: 42, snapshot_id: 11, book_id: 1 },
    fixture_test_data: true,
    citation_evidence_bindings: [],
  } satisfies ChapterFunctionsProductResponse,
  H_canceled: {
    result_status: "canceled",
    contract_version: "v2",
    coverage_scope: null,
    chapter_functions: null,
    items: [],
    next_cursor: null,
    total_chapters: 0,
    failure_message_safe: "本次全书分析任务已取消，章节功能未完成。",
    source_revision: { run_id: 42, snapshot_id: 11, book_id: 1 },
    fixture_test_data: true,
  } satisfies ChapterFunctionsProductResponse,
  I_conflict: productEnvelope(FIXTURE_A_AVAILABLE, {
    result_status: "conflict",
    conflict: {
      versions: [
        { version_id: "v-confirmed", label: "已确认", state: "confirmed" },
        { version_id: "v-candidate", label: "候选", state: "candidate" },
      ],
      current_pointer: "v-confirmed",
    },
  }),
  /** J — loading is a client view state; no envelope. */
  J_loading: null,
  /** K — absent → 404 CHAPTER_FUNCTIONS_RESULT_ABSENT */
  K_absent: null,
  L_long_book_page0: longBookPage(0),
  L_long_book_page1: longBookPage(1),
  M_function_filter_setup: productEnvelope(FIXTURE_A_AVAILABLE, {
    items: FIXTURE_A_AVAILABLE.chapters.filter((c) => c.primary_function === "setup"),
    total_chapters: 1,
    next_cursor: null,
  }),
  N_status_filter_observed: productEnvelope(FIXTURE_A_AVAILABLE, {
    items: FIXTURE_A_AVAILABLE.chapters.filter(
      (c) => c.observed_summary?.status === "observed",
    ),
    total_chapters: FIXTURE_A_AVAILABLE.chapters.length,
  }),
  O_invalid_cursor_error: {
    error_code: "CHAPTER_FUNCTIONS_INVALID_CURSOR",
    message: "分页游标无效，请清除筛选后重试",
  },
  P_unsupported_version: {
    result_status: "failed",
    contract_version: "v1",
    coverage_scope: null,
    chapter_functions: {
      contract_version: "v1",
      evidence_contract_version: "v1",
      coverage_scope: "full_selected_range",
      chapters: [],
    } as unknown as ChapterFunctionsResultV2,
    items: [],
    next_cursor: null,
    total_chapters: 0,
    failure_code: "CHAPTER_FN_UNSUPPORTED_VERSION",
    failure_message_safe: "不支持的章节功能合同版本",
    fixture_test_data: true,
  } satisfies ChapterFunctionsProductResponse,
  Q_evidence: productEnvelope(FIXTURE_B_PRIMARY_SECONDARY),
  R_wb21_context_available: productEnvelope(FIXTURE_R_WB21_CONTEXT_AVAILABLE),
  S_wb21_context_absent: productEnvelope(FIXTURE_S_WB21_CONTEXT_ABSENT),
  T_wb21_context_insufficient: productEnvelope(FIXTURE_T_WB21_CONTEXT_INSUFFICIENT),
  U_empty_label: productEnvelope(FIXTURE_U_EMPTY_LABEL),
  V_non_mainline: productEnvelope(FIXTURE_V_NON_MAINLINE),
  W_unknown: productEnvelope(FIXTURE_W_UNKNOWN),
};

/** Lab V1 adapter sample — NOT Free SoT. */
export const FIXTURE_LAB_V1_ADAPTER: LabChapterFunctionsResultV1 = {
  items: [
    {
      chapter_id: 1,
      chapter_order: 1,
      function_labels: ["setup", "transition"],
      change_summary: "lab adapter only",
      evidence_refs: [],
    },
  ],
  contract_version: "v1",
  adapted_from: "ChapterFunctionsResultV2",
  coverage_scope: "full_selected_range",
  result_status: "completed",
};
