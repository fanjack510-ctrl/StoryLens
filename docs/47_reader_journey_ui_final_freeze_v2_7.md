# docs/47｜Reader Journey UI Final Freeze v2.7

**版本：** Reader Journey UI Final Baseline v2.7  
**前置：** Phase 1C-C.2.7 Context Inspector Information Hierarchy 全部通过  
**范围：** 旅程分析页面生产运行文件最终冻结（展示与组合层）

## 1. 最终页面信息架构

上半 **Journey Overview**：标题「旅程分析」、紧凑章节结论条、Phase 导航、指标选择、图例、曲线（min-height 300px）、Scene 节奏带。  
下半 **单一 Context Inspector**：Scene / Phase / Question / Hook / Payoff / Risk 互斥；未选择时显示操作提示空状态。

## 2. 页面组件清单

见 `audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.7/reader-journey-ui-dependency-map-v2.7.json`（由真实相对 import 图生成）。

主要入口：

- `ReaderJourneySyncWorkspace`
- `ReaderJourneyWorkspace`
- `JourneySceneDetailPanel` + `inspectorShell`
- `journeySelectionTransaction` / `useJourneySelection`
- `exportJourneyPng`
- `readerJourney.css` / `syncWorkspace.css`

## 3. 六类 Inspector

统一骨架：Header → Primary Conclusion → Tabs/Sections → Evidence/Related → Empty/Error。  
纯展示组件位于 `inspectorShell.tsx`；业务选择语义不在此层。

## 4. 选择与滚动语义

- Scene 首次点击不回退（pendingProgrammaticSceneRef + Selection Transaction）
- Phase 点击不改 Scene
- Scroll Spy / Evidence 定位语义保持
- 禁止直接修改冻结交互文件，除非走变更包

## 5. URL 语义

Books / Standalone / 旧 `overview=questions|diagnosis` 兼容见路由基线 JSON。

## 6. 响应式规则

Phase：桌面四列 / 中宽横滚 / 窄屏下拉。  
Inspector：单列为主，页签可横滚，相关 Scene 窄屏列表化。

## 7. PNG 规则

仅导出 Overview（export root）；标题「旅程分析」。

## 8. UX 不变量

Manifest 记录 20 条 UX 不变量（标题唯一、Phase 布局、曲线高度、单一 Inspector、空状态不建 Run 等）。

## 9. Freeze 分类

| 分类 | 含义 |
|------|------|
| FROZEN_JOURNEY_COMPOSITION | 页面结构与分区组合 |
| FROZEN_JOURNEY_INTERACTION | Selection Transaction / Hook / URL 适配 |
| FROZEN_JOURNEY_VISUALIZATION | 曲线/指标/标记 tokens |
| FROZEN_JOURNEY_INSPECTOR | 六类详情与空/错状态 |
| FROZEN_JOURNEY_EXPORT | PNG 导出 |
| FROZEN_JOURNEY_PRESENTATION | CSS 与标签 |

## 10. 文件 Hash

`reader-journey-ui-final-freeze-v2.7.json`：每文件 `path` / `sha256` / `category` / `responsibility` / `approved_version` / `source_thaw` / `test_coverage`。

## 11. 路由基线

`reader-journey-ui-route-baseline-v2.7.json`

## 12. 视觉基线

`screenshots/`：

1. books-1920x1080-scene.png  
2. books-1280x720-phase.png  
3. books-1024x768-empty-state.png  
4. standalone-1920x1080-scene.png  
5. png-export-reader-journey-v2.7.png  

截图仅作视觉参考，不替代 DOM/E2E。

## 13. 测试基线

`reader-journey-ui-test-baseline-v2.7.json`：unit / e2e / gates 清单。

## 14. 未来变更规则

禁止直接修改冻结文件。  
必须新建 `reader-journey-ui-change-<version>.json`，记录原因、缺陷证据、允许文件与变化、回归测试、新哈希、是否升级 Final Baseline。  
不得原地覆盖 v2.7 Manifest。

## 15. 恢复与审计

```powershell
.\.venv\Scripts\python.exe .\scripts\check_reader_journey_ui_freeze.py
.\.venv\Scripts\python.exe .\scripts\check_reader_journey_ui_freeze.py --explain apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx
.\.venv\Scripts\python.exe .\scripts\check_reader_journey_ui_freeze.py --json
```

不匹配即非 0；无 LF 容错；不自动更新哈希。
