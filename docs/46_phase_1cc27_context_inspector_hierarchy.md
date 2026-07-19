# docs/46｜Phase 1C-C.2.7 Context Inspector Information Hierarchy

**阶段：** 上下文详情区信息层级与空状态优化（展示层）  
**非目标：** 不改分析数据、公式、选择语义、Scroll Spy、Evidence 映射、PNG 数据语义；不调用真实模型；不新建 Run。

## 1. 原 Inspector 信息问题

1. 标题、标签、字段与卡片过多，核心结论不突出。  
2. Scene / Phase / Question / Hook / Payoff / Risk 结构不统一。  
3. 空字段仍渲染标题或空容器，出现大片空白。  
4. 空状态仅「暂无数据」，缺少解释。  
5. Evidence 大卡片过重；下半区多层边框嵌套。

## 2. 六类对象字段映射

| 对象 | 渲染组件 | 一句话结论来源 | Header 元信息 |
|------|----------|----------------|---------------|
| Scene | `JourneySceneDetailPanel` | `scene_value_summary` | Phase · Scene ordinal；role pill |
| Phase | `JourneyPhaseDetailPanel` | `phase.summary` | title · Scene 范围 |
| Question | `JourneyQuestionInspectorPanel` | `primary_question` / `cluster_title` | 问题链 · 创建 Scene；lifecycle pill |
| Hook | `JourneyMarkerInspectorPanel` | `primary_hook.summary` / hooks[0] | Hook · Scene；type pill |
| Payoff | `JourneyMarkerInspectorPanel` | `primary_payoff.summary` / payoffs[0] | Payoff · Scene；type pill |
| Risk | `JourneyMarkerInspectorPanel` | `riskInterval.summary` / trigger | Risk · 区间；risk_type pill |

共享纯展示骨架：`inspectorShell.tsx`（Header / Conclusion / Section / Empty / Evidence / Related）。

## 3. 统一骨架

1. Inspector Header（sticky，52–64px）  
2. Primary Conclusion（既有字段，最多两行）  
3. Object Summary / 关键指标  
4. Inspector Tabs（Scene 五 / Phase 四；其余无独立页签）  
5. Tab Content（扁平 Section）  
6. Evidence / Related Objects  
7. Empty State 或 Error Boundary

## 4. Scene 最终结构

页签：概览 / 问题链 / 回报与钩子 / 写作技法 / 证据。  
概览：结论 → 结构等级 → Phase → 情绪 → 三项指标（牵引｜好奇｜紧张）→ 风险（空则不渲染）→ 写作建议。  
问题链 / Hook-Payoff / 技法：同类空小节不渲染；全空用统一空状态。  
Evidence：默认前 5 条，可「展开全部 N 条」。

## 5. Phase 最终结构

页签：阶段概览 / 问题与回报 / 节奏风险 / 相关 Scene。  
相关 Scene 为紧凑行列表，点击复用既有 `onSelectScene`。

## 6. Question / Hook / Payoff / Risk

按既有字段分层展示；缺失承接 / 前置 Hook 用审慎说明，不推断「失效」。  
生命周期中文：新建 / 延续 / 部分回答 / 回答 / 转化 / 悬而未决。

## 7. 标签减量

Header 最多 2 个 pill（role / lifecycle / type）。普通字段不用标签墙。

## 8. 空状态

`JourneyInspectorEmptyState`：`no-question-chain` / `no-hook-payoff` / `no-technique` / `no-evidence` / `no-risk` / `no-related-scenes` / `no-lifecycle` / `no-selection`。高度 56–96px。不创建 Run。

## 9. 错误状态

`JourneyDetailErrorBoundary` 与空状态分离；渲染异常不显示为「暂无数据」。

## 10. Evidence

紧凑行：paragraphId · kind · 短摘要 · 定位正文。定位语义不变。

## 11. 响应式

页签可横向滚动；相关 Scene 窄屏降级单列；Inspector 不挤压曲线（Overview 分区不变）。

## 12. v2-5 Thaw

`audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-5.json`  
purpose: `context-inspector-information-hierarchy-and-empty-states`  
允许：`inspectorShell.tsx`（新）、`JourneySceneDetailPanel.tsx`、`ReaderJourneyWorkspace.tsx`、`readerJourney.css`、`journeyUiLabels.ts`、`sceneDetailFields.tsx`。

禁止修改：`journeySelectionTransaction.ts`、`useJourneySelection.ts`、旧 Thaw、core freeze。

## 13. Freeze 检查

- `check_core_freeze`：FROZEN_CORE / CONTRACT modified=0  
- `check_ui_presentation_thaw`：含 v2-5，非白名单=0  

## 14. E2E

`apps/desktop/e2e/phase_1cc27_context_inspector_hierarchy.spec.ts`：Scene 概览、空问题链、技法 object、Evidence 展开定位、Phase 保 Scene、多 Inspector、未选择提示、三视口响应式。
