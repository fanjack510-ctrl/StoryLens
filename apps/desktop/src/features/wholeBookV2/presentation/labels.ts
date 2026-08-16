/** Wire-value → reader-facing label maps, shared by the on-screen report and the exported
 *  file. One vocabulary: if a label changes here it changes in both places, which is the
 *  point — an export that names things differently from the screen cannot be audited
 *  against it. */
import type { JourneyAxis, WholeBookAnalysisV2 } from "../contracts";

export const PACING_LABELS = ["剧情推进", "阅读张力", "情绪强度", "阅读动力", "钩子密度", "节奏速度"];

export const HEATMAP_DIMS: Array<{ key: keyof WholeBookAnalysisV2["chapters"]["heatmap"][number]; label: string }> = [
  { key: "mainline_progress", label: "主线推进" },
  { key: "character_development", label: "人物成长" },
  { key: "conflict", label: "冲突强度" },
  { key: "suspense", label: "悬念密度" },
  { key: "foreshadow", label: "伏笔铺设" },
  { key: "payoff", label: "回收兑现" },
  { key: "transition", label: "过渡衔接" },
];

export const STORYLINE_STATUS: Record<string, string> = {
  resolved: "已收束",
  open: "未收束",
  active: "进行中",
  abandoned: "已弃置",
};

export const JOURNEY_TAB: Record<JourneyAxis, string> = {
  cognition: "认知历程",
  ladder: "升级历程",
  screen_time: "戏份分布",
  none: "主角历程",
};

/** The backend types role as a free string; these are the values it actually emits. */
export const ROLE_LABEL: Record<string, string> = {
  protagonist: "主角",
  supporting: "配角",
  antagonist: "对手",
  mentor: "导师",
  ally: "盟友",
  foil: "镜像",
  narrator: "叙述者",
};

/** What each beat did to the question, as a reader would name it. */
export const SUSPENSE_BEATS: Record<string, string> = {
  hook: "抛出", clue: "线索", foreshadow: "伏笔", misdirection: "误导",
  partial_reveal: "部分揭示", reveal: "揭示", twist: "反转", payoff: "兑现",
};

export const DIMENSION_LABELS: Record<string, string> = {
  story_structure: "故事结构",
  protagonist_growth: "主角成长",
  character_relationships: "人物关系",
  suspense_payoff: "悬念回收",
  pacing: "节奏",
  chapter_efficiency: "章节效率",
};

/** Which row of the issue map each issue category lands on. Issue categories share the
 *  dimension vocabulary plus a few structural aliases the engine has emitted. */
export const CATEGORY_ROW: Record<string, string> = {
  structure: "结构",
  story_structure: "结构",
  character: "人物",
  character_relationships: "人物",
  protagonist_growth: "人物",
  suspense: "悬念",
  suspense_payoff: "悬念",
  pacing: "节奏",
  chapter_efficiency: "章节效率",
};
