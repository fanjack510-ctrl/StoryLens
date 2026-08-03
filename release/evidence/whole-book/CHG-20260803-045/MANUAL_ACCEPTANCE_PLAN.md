# MANUAL_ACCEPTANCE_PLAN — MG-V1.2.0-E2E-STABILIZATION

## Gate
MG-V1.2.0-E2E-STABILIZATION  
（本 CHG-045 **只规划**，不启动人工环境）

## Environment（未来 Integration 后）
- 隔离测试 DB（非正式 AppData）  
- Fake / Fixture Provider only  
- REAL PROVIDER CALLS：**0**  
- UI + API 本地端口另定  

## Checklist（最少）

| # | Item |
|---|---|
| 1 | 正式书籍入口进入 Free 全书页 |
| 2 | 四模块顺序打开（overview → characters_events → structure → chapter_functions） |
| 3 | 浏览器刷新后模块/关键状态保持 |
| 4 | 离开后重进：不新建 Run、不触发 Provider |
| 5 | Evidence 跳转精确高亮；返回保持模块 |
| 6 | 章节功能：分页/筛选/cursor/详情返回保持 |
| 7 | Pause / Resume / Cancel（Fake 可执行边界） |
| 8 | 冲突版本展示正确 |
| 9 | 费用估算展示；Consent 后行为正确 |
| 10 | Provider disabled 时正式启动被阻止 |
| 11 | 无购买 / License / 激活 UI |
| 12 | 无 Dev Harness 正式入口（生产构建或 PROD 模式验证） |
| 13 | Fixture Preview 有明确标识（若开启） |
| 14 | 1366 / 1920 无横向滚动 |

## Pass rule
全部 PASS 或书面 ABSENT（仅允许购买 UI / Dev 入口等产品禁止项）。  
任一项 FAIL → 门禁失败，不得标 verified。
