# docs/38｜Phase 1C-C.2.5.2 Reader Journey Context Inspector

**阶段：** 读者旅程统一上下文详情区与标签减量（展示层）  
**非目标：** 不改分析数据、公式、选择语义核心、Scroll Spy、Evidence 映射、导出数据语义；不调用真实模型；不新建 Run。

## 1. 问题

1. Phase 详情插在 Phase 结构带与曲线之间，挤压曲线。
2. Phase / Scene 两套详情争抢下半区。
3. 指标、图例、Scene 节点标签过密。
4. 首屏重点不清晰。

## 2. 布局原则

上半 **Journey Overview**：模式切换、精简/完整、摘要、Phase 结构带、指标、图例、曲线、薄节奏带。  
下半 **Context Inspector**：同一时间只显示一种 selection 详情。

Overview 默认约 55%–60%；Inspector 独立滚动，不得挤压曲线。

## 3. Context Inspector

`inspector=phase|scene|question|hook|payoff|risk` 为纯 UI 状态（与 `overview=` 同类），不新建第二套 activeScene / activePhase。

| 点击 | Overview | Inspector |
|------|----------|-----------|
| Phase | activePhase 高亮区间 | Phase 四页签 |
| Scene | activeScene + 正文定位 | Scene 五页签（既有） |
| 问题簇 / Hook / Payoff / Risk | 既有标记语义 | 对应详情，无覆盖曲线浮层 |

点击 Phase：**不**自动改写当前 Scene；**不**在结构带下方展开详情。

## 4. Phase 详情页签

1. 阶段概览  
2. 问题与回报  
3. 节奏风险  
4. 相关 Scene（点击进入 Scene 详情并定位正文）

## 5. Phase 结构带

仅：编号、短标题（最多两行）、Scene 范围、平均牵引。高度一致。

## 6. 指标减量

快捷：阅读牵引 / 好奇 / 紧张。  
更多指标 ▼：回报、钩子、掉线风险、情绪正负、情绪唤醒。  
底层指标与 metric URL 语义不变。

## 7. 图例

精简：当前 Scene / Hook / Payoff / Risk。  
完整：+ answered / transformed / Secondary / Beat / 派生标记。

## 8. Scene 节奏带

薄点状条：Core 大 / Secondary 中 / Beat 小；当前 Scene 高亮；保留点击定位。

## 9. PNG / 路由

PNG 仍只导出 Overview（export root）；独立结果路由与章节内嵌结果不变。

## 10. Freeze

沿用 v1+v2 展示白名单生产文件；测试文件 `phase_1cc252_*`。  
FROZEN_CORE / FROZEN_CONTRACT / 非白名单 REUSABLE_UI_LOGIC modified=0。  
真实模型请求 / Token / 费用 / 新 AnalysisRun / 新 ReaderJourneyRun = 0。  
Run #55 / JourneyRun #2 保持 succeeded。
