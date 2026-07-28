# MG-WB-1.3 FOUNDATION DIAGNOSTICS — Manual Test

## Prep
1. Use worktree `D:\Dstorylens-wt-whole-book-v120-integration`
2. Enable flag: `VITE_WHOLE_BOOK_DIAGNOSTICS_ENABLED=true` (dev only)
3. Start API against a **temporary** SQLite DB (never formal AppData)
4. Open `/dev/whole-book-diagnostics`

## Checklist
- [ ] Banner shows 全书分析开发诊断页 + 不会调用大模型
- [ ] Select a local book; see chapter count, character count, book_revision_hash
- [ ] Create/reuse Snapshot; note reused badge, version, content_hash, chapter/paragraph/character counts
- [ ] View chapters + first 20 paragraphs (read-only)
- [ ] Create test Run (native + fixture); see 7 stages; snapshot stage completed
- [ ] Start / Pause / Resume / Cancel only change status; Provider calls stay 0
- [ ] Generate windows; coverage 100%, uncovered 0, order valid
- [ ] Inspect a window: chapter range, overlap, paragraph previews (local only)
- [ ] Confirm page is NOT in primary nav / library menus / settings

## Pass criteria
All boxes checked; no formal DB writes; no real provider calls.

## After PASS
Mark WB-1.1 / WB-1.2 / WB-1.3 as verified. Do not start WB-1.4.
