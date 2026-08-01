# CHG-20260731-029 Manual Smoke Environment

## Status
READY (servers started; checklist NOT executed by agent)

## Isolation
| Item | Value |
| --- | --- |
| Public worktree | `D:\Dstorylens-wt-1.2.0-after-1.1.2` @ `integration/1.2.0-after-1.1.2` |
| Private worktree | `D:\Dstorylens-private-wt-1.2.0-after-1.1.2` @ `integration/1.2.0-private-after-1.1.2` |
| Temp dir | `C:\Users\msi\AppData\Local\Temp\storylens-chg029\` |
| SQLite | `chg029_smoke.db` (copy of Wave D isolation DB; **not** AppData formal DB) |
| API | `http://127.0.0.1:8002` |
| UI | `http://127.0.0.1:1422` |
| Real provider | **disabled** (`STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED=false`) |
| Wave D ports | left alone (`8000` / `1421`) |

## Flags
```
STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED=true
STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED=true
STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED=false
VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED=true
VITE_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED=true
VITE_API_BASE_URL=http://127.0.0.1:8002
```

## Checklist (manual; pending)
1. 单章场景分析入口
2. 自定义场景拆分
3. 场景任务中断
4. 阅读旅程中断恢复
5. 恢复成功自动进入结果
6. 右侧和顶部 Journey 入口
7. 全书分析入口
8. Free 4 个模块
9. 演示数据标识
10. 全书总览 9 项
11. 人物与关键事件
12. Evidence Deep Link
13. 费用估算与确认
14. 无 Pro 购买界面

## Task control
- PAUSE / RESUME / CANCEL: **AUTOMATED PASS** / **MANUAL NOT EXECUTED**
- Exception: `EXC-WB-FREE-WAVE-D-001`

## Constraints
- No Push / Tag / Release / installer build
- No WB-2.1 implementation
- No formal AppData database writes
- No real Provider calls for this gate
