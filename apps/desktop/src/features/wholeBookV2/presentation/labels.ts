/** Wire-value → reader-facing label maps, shared by the on-screen report and the exported
 *  file. One vocabulary: if a label changes here it changes in both places, which is the
 *  point — an export that names things differently from the screen cannot be audited
 *  against it. */
import type { JourneyAxis, WholeBookAnalysisV2 } from "../contracts";

/** The three pacing curves, and the key each reads.
 *
 *  Three, not six. The other three were the same counters combined a second time — 阅读动力 was
 *  literally `2×钩子 + 信息节拍`, so it tracked the two curves beside it at r=0.73 and r=0.65 —
 *  and six lines over ninety points is a ball of wool whichever colours it is drawn in. */
export const PACING_SERIES: Array<{
  key: "plot_progress" | "hook_density" | "emotion";
  label: string;
  /** What was counted, before ranking. Shown to the reader, because "剧情推进 93" means
   *  nothing until you know it is a rank among this book's own chapters. */
  measures: string;
}> = [
  { key: "plot_progress", label: "剧情推进", measures: "每章新信息节拍数" },
  { key: "hook_density", label: "钩子密度", measures: "章末留钩的比例" },
  { key: "emotion", label: "情绪浓度", measures: "每章心理描写段落数" },
];

export const PACING_LABELS = PACING_SERIES.map((s) => s.label);

/** These are **not** scores. Each figure is the chapter's percentile rank within this book, so
 *  the column always spans 0–100 no matter how even the book is, and two books' numbers cannot
 *  be compared. Said on the page, because "满分 100" is the reading anyone would default to. */
export const PACING_SCALE_NOTE =
  "0–100 是本书内部的百分位排名，不是评分：90 表示「比本书 90% 的章节更高」。因此区间必然铺满 0–100，且不同书之间不可比较。";

/** Each column is a counted average, and they are on different scales by nature — a chapter has
 *  about twenty dialogue paragraphs and either zero or one hook. The label says what was
 *  counted rather than what it might mean, because 「冲突强度」 over a count of action
 *  paragraphs is a claim the number does not support. */
export const HEATMAP_DIMS: Array<{
  key: keyof WholeBookAnalysisV2["chapters"]["heatmap"][number];
  label: string;
  unit: string;
}> = [
  { key: "mainline_progress", label: "新信息节拍", unit: "条/章" },
  { key: "character_development", label: "心理描写", unit: "段/章" },
  { key: "conflict", label: "动作段落", unit: "段/章" },
  { key: "transition", label: "对话段落", unit: "段/章" },
  { key: "suspense", label: "章末留钩", unit: "占比" },
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
  relationship: "关系历程",
  stakes: "得失历程",
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

/** 模型没答上来时留下的占位词。它们不是值。
 *
 *  《系统豪横》第 18 次运行里，二十二个人物有十二个的「与主角的关系」是字面量 `unknown`，
 *  报告照印十二行。读者拿 `unknown` 做不了任何事，核不了，也分不清它和一个 bug 的区别。
 *
 *  同样的词也出现在屏幕上的人物档案里（十二人中六人），因为这条规则原先只写在 PDF 导出
 *  那一侧。现在放在这里，屏幕、HTML 导出、PDF 三处共用一份定义。
 */
const PLACEHOLDER = /^(unknown|unspecified|未知|不详|不明|待定|暂无|n\/?a|null|none|nan|无|-{1,2}|—|\.+)$/i;

/** True when the value is a placeholder rather than something the book actually says. */
export function saidNothing(value: unknown): boolean {
  const text = String(value ?? "").trim();
  return !text || PLACEHOLDER.test(text);
}
