# DEV_HARNESS_DECISION — CHG-20260803-042

Route: `/dev/whole-book-free-chapter-functions-harness`

DECISION: RETAIN behind `import.meta.env.DEV` gate (same pattern as diagnostics).
- Not in Free product nav
- Not production build entry
- Playwright continues to use Vite DEV server
