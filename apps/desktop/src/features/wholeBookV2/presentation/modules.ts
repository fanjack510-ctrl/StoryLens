export type ModuleKey =
  | "overview"
  | "story_breakdown"
  | "story"
  | "characters"
  | "suspense"
  | "pacing"
  | "chapters"
  | "assessment";

export const MODULES: Array<{
  key: ModuleKey;
  label: string;
  description: string;
}> = [
  {
    key: "overview",
    label: "全书总览",
    description: "快速理解作品画像、故事核心、长线演变与最终落点。",
  },
  {
    key: "story_breakdown",
    label: "拆文",
    description: "起承转合、最打动人的瞬间、每章留下的问题、可以拿走的手法与配角功能。",
  },
  {
    key: "story",
    label: "故事",
    description: "查看结构阶段、主线支线、因果链与时间线。",
  },
  {
    key: "characters",
    label: "人物",
    description: "追踪人物系统、主角完整成长与关系生命周期。",
  },
  {
    key: "suspense",
    label: "悬念",
    description: "检查核心问题从提出、误导到反转和最终回收的全过程。",
  },
  {
    key: "pacing",
    label: "节奏",
    description: "把阅读曲线与结构阶段、关键章节放在一起理解。",
  },
  {
    key: "chapters",
    label: "章节",
    description: "以聚合窗口观察章节功能分布，再下钻代表章节。",
  },
  {
    key: "assessment",
    label: "综合诊断",
    description: "总结全书优势、问题严重度、集中区间与修改优先级。",
  },
];

export const MODULE_LABELS: Record<ModuleKey, string> = Object.fromEntries(
  MODULES.map((m) => [m.key, m.label]),
) as Record<ModuleKey, string>;

export const MODULE_DESCRIPTIONS: Record<ModuleKey, string> = Object.fromEntries(
  MODULES.map((m) => [m.key, m.description]),
) as Record<ModuleKey, string>;


/** Which modules a reading actually fills.
 *
 *  拆文 and 评测 share the extraction layers, so 故事 / 人物 / 悬念 / 节奏 / 章节 come out of
 *  both. What differs is the top: 评测 produces 全书总览 and 综合诊断; 拆文 produces its own
 *  section and leaves those two almost entirely empty — `overview` at 5 of 19 fields and
 *  `assessment` at 1 of 9 on a real run.
 *
 *  Showing every module regardless of mode is how a 拆文 run came to display two blank pages
 *  while the section it had actually filled had nowhere to appear at all.
 */
export function modulesForDocument(hasBreakdown: boolean): typeof MODULES {
  return MODULES.filter((m) => {
    if (m.key === "story_breakdown") return hasBreakdown;
    if (m.key === "overview" || m.key === "assessment") return !hasBreakdown;
    return true;
  });
}
