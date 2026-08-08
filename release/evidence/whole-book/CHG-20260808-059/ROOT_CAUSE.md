# CHG-20260808-059 — Root Cause

## Issue
Installed StoryLens 1.2.0 launches normally, but Free「全书分析」entry is missing from production UI.

## Root cause
Production / Tauri installer builds left Free whole-book **disabled by default**:

1. **Desktop**: `vite.config.ts` defaulted `VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED` / `__STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED__` to **false**.
2. **Desktop runtime**: `isWholeBookFreeProductEnabled()` defaulted **OFF** when env/define unset.
3. **Entry gate**: `WholeBookFreeEntry` returns `null` when the flag is false (Book workspace secondary toolbar).
4. **Backend (would break create even if UI forced on)**: `STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED` and `STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED` also defaulted **false**.

E2E/Manual previously set `VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED=true` explicitly; the installer build did **not**.

## Not the cause
- Missing route source (`/books/:bookId/whole-book` was present)
- Missing product modules
- Need for Dev Harness / Fixture / developer mode
- IA redesign

## Product requirement (frozen)
V1.2.0 Free installer must default Free Whole-Book Product **ENABLED** with four modules; no user env/config required.
