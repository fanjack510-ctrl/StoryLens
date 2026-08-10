export type ModuleKey =
  | "overview"
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
