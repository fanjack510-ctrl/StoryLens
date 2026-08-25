import type { EntitlementSnapshot } from "./entitlementApi";

export type ProductEdition = "free" | "pro";

export type ProductEditionState = {
  edition: ProductEdition;
  /** Short UI label: 免费版 | 专业版 */
  edition_display_name: string;
  /** Full product line: StoryLens 免费版 | StoryLens Pro */
  product_line_name: string;
  is_pro: boolean;
  license_status: "unknown" | "free" | "active" | "error";
  entitlement_source: string;
  major_version: number | null;
  application_version: string;
  loaded: boolean;
  error: string | null;
  /** Soft user-facing note when entitlement cannot be read (never deletes licenses). */
  user_error_message: string | null;
};

export const ENTITLEMENTS_QUERY_KEY = ["entitlements"] as const;

export function editionDisplayName(edition: ProductEdition): string {
  return edition === "pro" ? "专业版" : "免费版";
}

export function productLineName(edition: ProductEdition): string {
  return edition === "pro" ? "StoryLens Pro" : "StoryLens 免费版";
}

/** Build product identity from entitlement snapshot. Fail-closed to free when unloaded/error. */
export function buildProductEditionState(input: {
  snapshot?: EntitlementSnapshot | null;
  loaded: boolean;
  error?: unknown;
  applicationVersion: string;
}): ProductEditionState {
  const { snapshot, loaded, applicationVersion } = input;
  const hasError = Boolean(input.error);
  if (!loaded) {
    return {
      edition: "free",
      edition_display_name: editionDisplayName("free"),
      product_line_name: productLineName("free"),
      is_pro: false,
      license_status: "unknown",
      entitlement_source: "pending",
      major_version: null,
      application_version: applicationVersion,
      loaded: false,
      error: null,
      user_error_message: null,
    };
  }
  if (hasError && !snapshot) {
    return {
      edition: "free",
      edition_display_name: editionDisplayName("free"),
      product_line_name: productLineName("free"),
      is_pro: false,
      license_status: "error",
      entitlement_source: "none",
      major_version: null,
      application_version: applicationVersion,
      loaded: true,
      error: input.error instanceof Error ? input.error.message : "entitlement_unavailable",
      user_error_message: "暂时无法读取专业版授权状态。",
    };
  }
  const isPro = Boolean(snapshot?.pro_active && snapshot.edition === "pro");
  const edition: ProductEdition = isPro ? "pro" : "free";
  return {
    edition,
    edition_display_name: editionDisplayName(edition),
    product_line_name: productLineName(edition),
    is_pro: isPro,
    license_status: isPro ? "active" : "free",
    entitlement_source: isPro ? "signed_local_license" : "none",
    major_version: snapshot?.major_version ?? null,
    application_version: applicationVersion,
    loaded: true,
    error: hasError ? "entitlement_partial_error" : null,
    user_error_message: hasError ? "暂时无法读取专业版授权状态。" : null,
  };
}

export function documentTitleForEdition(
  edition: ProductEdition,
  pageTitle?: string | null,
): string {
  const base = edition === "pro" ? "StoryLens Pro" : "StoryLens";
  const page = (pageTitle || "").trim();
  return page ? `${page} · ${base}` : base;
}

export const PRO_CAPABILITY_LABELS: Record<string, string> = {
  whole_book_analysis: "整书分析（Legacy）",
  narrative_asset_library: "叙事资产库",
  story_lab: "故事实验台",
  cross_book_search: "找相似写法",
  advanced_export: "进阶导出",
  pro_whole_book_insights: "章节精细分析覆盖（Legacy）",
  whole_book_native: "原生全书分析",
  whole_book_enhanced: "精细增强分析",
  chapter_aggregate_insights: "章节精细分析覆盖",
  common_patterns: "共性视图",
  knowledge_extraction: "从全书提取素材",
  book_skill_generation: "生成作品 Skill",
};

/** 历史私有分析引擎的总开关；当前五项产品级 Pro 权限不依赖此开关。 */
export const PRO_CAPABILITIES_SHIPPED = false;
