# REFRESH_REENTRY_RESTART_AUDIT — CHG-20260803-045

## Browser refresh

| State | Status | Notes |
|---|---|---|
| 当前书籍 | ALREADY COMPLETE | route `/books/:bookId/whole-book` |
| 当前模块 | PARTIAL | `?module=`；overview/chars 深链返回弱 |
| run_id | PARTIAL | 来自 prepare latest/recoverable；非 URL |
| CF 筛选 / cursor / detail | PARTIAL | restoreFunction/Status/Cursor 实现；刷新全量测缺 |
| conflict | PARTIAL | API 驱动；刷新断言缺 |

## Leave page & reenter

| Behavior | Status |
|---|---|
| 自动读有效 Run | ALREADY COMPLETE（prepare） |
| 不重新创建 Run | PARTIAL — 依赖 UI 不点创建；缺自动测 |
| 不触发 Provider | PARTIAL — fixture/real flags；reentry 测缺 |
| 终态正确显示 | PARTIAL |

## App / Sidecar restart（隔离测试 DB）

| Behavior | Status |
|---|---|
| running/paused/interrupted 恢复展示 | PARTIAL — `recoverable_run`；whole-book 重启套件缺 |
| 不自动调用 Provider | ALREADY COMPLETE（默认 real create blocked） |
| completed 可读 | ALREADY COMPLETE（DB） |
| canceled 不复活 | PARTIAL — 需测 |
| failed 不显示 running | PARTIAL |
| stale terminal 不被 ProgressCard 覆盖 | PARTIAL — 对齐 CHG-029 Journey 规则到 Free 页 |

## Wave 1 Fake-only
本 Wave **禁止真实模型**；重启测用 Fake/Fixture + 隔离 DB。

## Gaps → Wave 1
1. 刷新保留 module + CF restore* 自动化  
2. 重进不 create / 不 invoke  
3. Sidecar/API 进程重启后 Free prepare 状态矩阵（隔离 DB）  
