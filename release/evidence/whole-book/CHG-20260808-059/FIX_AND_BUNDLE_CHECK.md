# CHG-20260808-059 — Fix & Production Bundle Check

## Fix (minimal)
| Layer | Change |
|-------|--------|
| `apps/desktop/vite.config.ts` | Free product default ON |
| `apps/desktop/src/services/wholeBookFreeProductFlag.ts` | Runtime default ON |
| `apps/api/.../whole_book_free_product_v1_service.py` | FREE_PRODUCT default true |
| `apps/api/.../whole_book_minimal_helpers_v1.py` | REAL_PROVIDER default true |
| `apps/desktop/src-tauri/src/backend.rs` | Sidecar spawn sets both true |

Fixture / diagnostics / Dev harness: remain OFF.

## Formal entry (unchanged IA)
- Book workspace secondary toolbar → 「全书分析」
- Route: `/books/:bookId/whole-book`

## Verification
| Check | Result |
|-------|--------|
| Typecheck | PASS |
| Desktop production + Tauri NSIS | PASS |
| WHOLE BOOK ROUTE | PRESENT |
| WHOLE BOOK ENTRY | PRESENT |
| DEV `/dev/whole-book-*` | ABSENT |
| Fake Provider UI | ABSENT |
| MANUAL INSTALLED UI | PASS |

## New installer (outside repo)
`D:\StoryLens-Local-Evidence\v1.2.0-manual-acceptance-2\StoryLens_1.2.0_x64-setup.exe`
