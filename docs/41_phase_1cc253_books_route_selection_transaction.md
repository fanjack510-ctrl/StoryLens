# docs/41｜Phase 1C-C.2.5.3 Books Route Selection Transaction

**性质：** 展示层 URL 原子提交修复。不改 `useJourneySelection`、不改 Freeze Manifest、不写库、不调模型。

## 1. 竞态根因

一次 Curve/Rhythm Scene 点击会触发 **至少两次** `setSearchParams`：

1. `ReaderJourneyWorkspace.handleSelectScene` → `onSelectionChange` → `useJourneySelection.syncUrl`  
   - 使用 **render 闭包中的旧 `searchParams` 快照**（非函数式更新）写入 `scene` / `paragraph` / `metric`  
   - **不写** `inspector`
2. 同一次 handler 再调用 `setInspectorType("scene")` → 另一次 `setSearchParams`  
   - 虽为函数式 `prev => …`，但在 React Router 导航交错时，可能基于仍含 **旧 scene** 的 `prev` 提交  
   - 结果：`inspector=scene` 保留，但 `scene` 被写回旧值（例如 12）

Books 内嵌路由上该竞态更易复现（与独立结果路由共享同一 Workspace/Sync 代码，但 Books 另有 `resultTab→tab` 等 URL 别名 effect）。

## 2. 原 URL 写入链（Curve Scene）

```
click journey-curve-node-N
  → handleSelectScene
    → onSelectionChange({ activeSceneOrdinal, activePhaseOrdinal, source })
        → SyncWorkspace.selectPhase/selectSceneByOrdinal
          → applyPatch → syncUrl(stale snapshot)     // write #1
    → onSelectScene(scene_id)  // 可能因 visualization.scene_id 与 results.scene.id 不一致而 no-op
    → setInspectorType("scene")                      // write #2（竞态）
```

Rhythm 路径相同（`source=journey_rhythm`）。Inspector 标记（hook/payoff/risk）同样是 selection + 单独 inspector 写入。

## 3. 新事务模型

新增纯展示 helper：`journeySelectionTransaction.ts`

- `JourneySelectionIntent`：一次用户动作的完整意图（非第二套 JourneySelectionState）
- `applyJourneySelectionIntent(prev, intent)`：从 **最新** `URLSearchParams` 合并相关键
- Workspace / SyncWorkspace：`commitSelectionIntent` → `setSearchParams(prev => apply…(prev, intent), { replace: true })`  
  作为 **权威最终写入**，显式带上 `scene` + `paragraph` + `inspector`（或 Phase 的 preserveScene）

`useJourneySelection` **未修改**；syncUrl 仍可能先写一次，但权威 commit 覆盖为一致状态。

## 4–7. 规则摘要

| 动作 | 规则 |
|------|------|
| Curve / Rhythm | `inspector=scene`；更新 scene/paragraph；一次权威 commit |
| Phase | `inspector=phase`；**不改** scene/paragraph；不滚到 Phase 首 Scene |
| Evidence | 更新 scene/paragraph；**保留**当前 inspector |
| Scroll Spy | 更新 scene/paragraph；保留 inspector；仍用既有 ~600ms 抑制 |

## 8. Scroll Spy 协调

程序点击仍先 `beginProgrammaticScroll()`；权威 URL commit 不延长抑制窗口。

## 9. Back / Forward

高频定位使用 `replace: true`（与既有 syncUrl 一致）。正文 Scene header 选择同样 replace；E2E 用连续 header 点击 + `goBack`/`goForward` 验证 URL↔详情一致（若历史被 replace 折叠，则以最终 URL 与刷新恢复为准）。

## 10. Books vs 独立路由

同一事务 helper；Books 的 `resultTab` 在 commit 时规范为 `tab=reader-journey`。独立 `/analysis-runs/.../results` 参数语义不变。

## 11. v2-3 Thaw

`audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-3.json`  
白名单：`journeySelectionTransaction.ts`、`ReaderJourneyWorkspace.tsx`、`ReaderJourneySyncWorkspace.tsx`  
禁止把 `useJourneySelection` 加入白名单。

## 14. 程序滚动 vs Scroll Spy 回写（2.5.3 补丁）

根因：程序滚动使用 `behavior: "smooth"`，常超过 `useJourneySelection` 的 600ms 抑制窗；中途视口仍在 Scene N-1，Scroll Spy + `commitSelectionIntent` 把 URL 写回 N-1。第二次点击时滚动已稳，才成功。

修复（仍不改 `useJourneySelection` / 不改 600ms 常量）：

1. 程序滚动改为 `behavior: "auto"`（瞬时定位）；
2. SyncWorkspace 增加 `pendingProgrammaticSceneRef`：程序选中 Scene N 后，忽略不等于 N 的 Spy 提交，直到看到 N 或 2s 超时。
