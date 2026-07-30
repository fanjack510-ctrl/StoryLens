# CHG-20260730-017 Disposition Audit (STOP GATE)

Date：2026-07-30  
Context：CHG-20260730-019 / RC.5 integration train  
Trigger：§二 + stop condition「未验收 CHG-017 被纳入」

## User clarification

不同截图属于不同任务。本次实际缺陷是：

> 当前 Journey 已运行，但页面仍显示旧恢复提示。

该缺陷由 **CHG-20260730-018** 覆盖。

## Disposition rule applied

Registry 不支持 `superseded` / `cancelled` 字面状态；最接近且可用的是 `deferred`。  
但本 Change **已产生产品代码且已在 `hotfix/1.1.2` HEAD 可达**，因此 **不得** 按「仅登记未实施」路径静默 deferred/剔除，也 **不得** 静默纳入 RC.5。  
按指令 **停止并等待人工判断**。

## Location

| Item | Value |
|------|--------|
| Worktree（代码已合入） | `D:\Dstorylens-wt-hotfix-1.1.2-integration` |
| Branch | `hotfix/1.1.2` |
| Product commit | `834cb3401945ca93729fe4adfb96b195e3a64647` |
| Ancestor of current HEAD | **YES** (`git merge-base --is-ancestor` exit 0) |
| Registry status | `tested`（**未** verified） |
| `include_in_next_release` | `true` |
| In `release/unreleased.json` | **YES** |

## Product commits / files (CHG-017)

Primary product commit message：

```text
fix(chapter): hide journey navigation during scene analysis
```

Modified / added files in `834cb34`：

- `apps/api/tests/test_journey_nav_visibility_chg017.py` (added)
- `apps/desktop/src/components/analysis/SceneBoundaryNavigation.chg041.test.tsx`
- `apps/desktop/src/components/layout/WorkspaceViewSwitcher.tsx`
- `apps/desktop/src/pages/BookRoutePage.journeyNav.test.tsx` (added)
- `apps/desktop/src/pages/BookRoutePage.readerJourneyResume.test.tsx`
- `apps/desktop/src/pages/BookRoutePage.tsx`
- `apps/desktop/src/services/chapterAnalysisPresentation.journeyNav.test.ts` (added)
- `apps/desktop/src/services/chapterAnalysisPresentation.ts`
- `release/changes/CHG-20260730-017.json`
- `release/evidence/hotfix/1.1.2/CHG-20260730-017/*`
- `release/unreleased.json`

Follow-up docs commits also exist on the same branch (`ea1944e`, `d7635a7`, plus later attach commits).

## Behavior difference vs CHG-018

| Concern | CHG-017 | CHG-018 |
|---------|---------|---------|
| Problem framed | 场景分析期间仍显示「阅读旅程」入口 / 误入「尚未开始」页 | Active Journey 时仍显示旧「分析已暂停 / 修复并继续」 |
| Main UX change | `show_journey_nav` 仅允许 `journey_*`；深链重定向到 confirm/progress | Active 时强制 `showRecoveryCard=false`；Running 优先于 stale paused |
| New workflow states | `journey_starting`, `waiting_scene_analysis` | 复用/强化 active flags：`is_journey_active` / resume/stop flags |
| Recovery Plan backend | 未作为主修复面 | Active ⇒ `user_status=running`；resume ⇒ `already_running` / `already_resuming` |
| Overlap | 两者都改了 `chapterAnalysisPresentation.ts` 与 `BookRoutePage.tsx` | 018 在 017 之上继续改同一文件 |

当前 HEAD 仍保留 017 的导航门禁行为（`shouldShowJourneyNav` / `JOURNEY_NAV_WORKFLOW_STATES` / deep-link redirect）。

## Why RC.5 is blocked

1. CHG-017 **不是**「仅登记、无产品代码」——不能按 superseded-only 路径处理并假装不存在。  
2. CHG-017 **已经在** `hotfix/1.1.2` 历史中；任何从当前 HEAD 构建的 RC.5 都会带上 017 代码。  
3. 指令明确：**不得把未验收的 CHG-017 自动带入 RC.5**；遇此情况必须停止。

## Options needing human decision

1. **保留 017 代码**：补做 / 确认 MG-CHG-20260730-017，再 mark `verified` 并正式纳入 RC.5。  
2. **剔除 017 产品行为**：从 `hotfix/1.1.2` 回退/还原 017 对 nav/presentation 的行为变更（需明确是否保留测试与证据），再将 Registry 标为 `deferred` 并 `include_in_next_release=false`，记录 `superseded_by=CHG-20260730-018`（注：deferred 且 commits 仍在 HEAD 时，Registry check 可能要求 feature-flag 说明或真正移出代码）。  
3. **折中**：保留无害的 nav 收敛，但单独书面确认 017 不作为本轮缺陷修复依据，仍需对其产品行为做验收或显式 waiver。

## Stopped before

- CHG-015/018 → verified（015 此前已是 verified；018 仍为 tested，MG PASS 证据已写入但未 mark verified）  
- 创建 CHG-019  
- 构建 1.1.2-rc.5  
- 安装态自动验收  

等待人工判断后再继续。
