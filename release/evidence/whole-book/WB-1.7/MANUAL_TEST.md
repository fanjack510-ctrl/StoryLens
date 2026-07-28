# MG-WB-FREE-WAVE-D — Manual UI Acceptance

## Prep
1. Worktree: `D:\Dstorylens-wt-whole-book-v120-integration`
2. Enable:
   - `VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED=true`
   - `VITE_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED=true`
   - `STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED=true`
   - `STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED=true`
3. Use temporary SQLite only (never formal AppData)
4. Keep real provider flags OFF

## Checklist
- [ ] Book detail shows 全书分析 entry (not primary nav)
- [ ] Page is formal product UI (not diagnostics)
- [ ] Fixture preview clearly labelled / yellow banner
- [ ] Cost estimate + consent checkbox on prepare
- [ ] Progress stages readable in Chinese
- [ ] Pause / Resume / Cancel behave correctly
- [ ] Overview nine claims render
- [ ] Characters/events from overview IDs
- [ ] Evidence opens reader with highlight (or clear stale message)
- [ ] Structure + chapter functions show 开发中
- [ ] Pro module shows 后续版本开放 (no purchase)
- [ ] Real provider calls = 0
- [ ] Formal AppData writes = 0

## After PASS
Mark WB-1.7 and WB-1.8 verified. Do not start WB-2.1.
