# MG-WB-1.3 FOUNDATION DIAGNOSTICS — Manual Test

## Result
**PASS**（2026-07-28）

## Prep
1. Use worktree `D:\Dstorylens-wt-whole-book-v120-integration`
2. Enable flag: `VITE_WHOLE_BOOK_DIAGNOSTICS_ENABLED=true` (dev only)
3. Start API against a **temporary** SQLite DB (never formal AppData)
4. Open `/dev/whole-book-diagnostics`

## Checklist
- [x] Banner shows 全书分析开发诊断页 + 不会调用大模型
- [x] Select a local book; see chapter count, character count, book_revision_hash
- [x] Create/reuse Snapshot; note reused badge, version, content_hash, chapter/paragraph/character counts
- [x] View chapters + first 20 paragraphs (read-only)
- [x] Create test Run (native + fixture); see 7 stages; snapshot stage completed
- [x] Start / Pause / Resume / Cancel only change status; Provider calls stay 0
- [x] Generate windows; coverage 100%, uncovered 0, order valid
- [x] Inspect a window: chapter range, overlap, paragraph previews (local only)
- [x] Confirm page is NOT in primary nav / library menus / settings

## Observed metrics
- Snapshot 创建与复用正常；status=completed；章节/段落/字符数正确
- Run 与 7 个 Stage 展示正常
- 窗口数量：188
- 总段落：77749
- 唯一覆盖：77749
- 重复计数：6149
- 遗漏：0
- 覆盖率：100%
- 顺序有效：是
- Provider 调用：0
- 正式全书入口：仍未开放

## After PASS
- WB-1.1 / WB-1.2 / WB-1.3 → verified
- 允许进入 WB-1.4-MIN-ENTITY-EVENT
- 不得自动实施 WB-1.4；等待下一份详细实施 Prompt
