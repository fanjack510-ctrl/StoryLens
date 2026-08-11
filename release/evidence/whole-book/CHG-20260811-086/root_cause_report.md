# CHG-20260811-086 — Whole-Book V2 end-to-end root cause

Forensic basis: read-only inspection of the packaged sidecar logs
(`%LOCALAPPDATA%\StoryLens\logs\sidecar.log`, session 2026-08-11 09:58:15 → 10:16:34)
and a read-only (`mode=ro`, `PRAGMA query_only=1`) query of the user database.
Zero real provider calls and zero formal-database writes were made during this
investigation.

## Real execution timeline (WholeBookRun 12, book 2, 542 ch / 2,901,455 chars)

| Time (local) | Event | Evidence |
| --- | --- | --- |
| 00:23:12 | Run 11 created → analysis_run 13 | `whole_book_runs` |
| 00:23:39–00:28:57 | 15/15 windows extracted, all `finish_reason=stop` | `model_invocations` 403–417 (2,190,091 in / 31,810 out) |
| — | Run 11 fails at `windowing` / `WHOLE_BOOK_BACKGROUND_FAILED` | `whole_book_runs` |
| 01:58:42 | Run 12 created → analysis_run 14, `previous_run_id=None` | `whole_book_runs` |
| 01:59:02–02:02:31 | Windows 1–12 **re-extracted** — input-token counts identical to 403–414 | `model_invocations` 418–429 |
| 02:03:02 | `window:W-1753-1791…: TRUNCATED_JSON` | sidecar.log:812 |
| 02:04:21 | Resume → `ValueError: window extraction requires evidence_ids from catalog` | sidecar.log:5874 |
| 02:05:29 | Same window retried: `finish_reason=length`, `output_tokens=4000` | `model_invocations` 430 |
| 02:05:50–02:07:09 | Windows 14–15 complete → 15 windows + 7 topics persisted | 22 `v2_intermediate_asset` rows |
| 02:07:09 | **Last provider call of the session** | `model_invocations` 432 |
| 02:07:09 | `overview_type: CONTEXT_UNSAFE: estimated tokens 123368 exceed safe context` | sidecar.log:7844 |
| 02:08:20–02:16 | 33 identical failures ~0.5 s apart, **zero provider calls** | log; `resume_count=35` |
| 02:16:34 | `sqlite3.OperationalError: database is locked` on a trivial INSERT | log tail |

## Primary root cause

`synthesis_payload_from_intermediates()` produced a single payload — all seven
topic intermediates plus the full 542-entry chapter catalog — and `analyze()`
handed that same payload to *every* synthesis unit. At 542 chapters the prompt
reached 238,736 chars, so `_call()` computed
`len(prompt)//2 + max_output_tokens = 123,368` against a safe context of
`128,000 − 8,000 = 120,000` and raised `CONTEXT_UNSAFE` **before issuing any HTTP
request**. The failure is deterministic, which is why CHG-085's resume logic —
which worked correctly, restoring all 15 paid windows in about half a second —
simply re-hit the same wall 33 times.

The planner could not detect this: `build_token_plan()` estimated synthesis input
as `min(budget.safe_input_capacity, max(2_000, max_window_input // 2))`. Because
of the `min(...)` clamp, `context_safe` can never evaluate to `"NO"` on account of
synthesis, so `assert_context_safe()` passed at plan time while the executor
rejected the identical run.

## Contributing root causes

1. **`pacing` was mathematically unsatisfiable.** `PacingSynthesisUnit` required
   `chapters.functions` covering all 542 chapters (enforced by
   `_validate_business`) inside a single `max_output_tokens=4000` response —
   realistically ≥32,000 output tokens. It had never been reached because
   `overview_type` failed first, so fixing only the context bug would have moved
   the failure rather than removed it.
2. **Duplicate payment.** `previous_run_id` was derived only from *completed*
   runs. Run 11 was `failed`, so run 12 re-bought all 15 windows. Actual spend on
   2026-08-11 was 4,380,182 input + 66,128 output tokens — roughly double the
   ~2.30 CNY the product reported.
3. **Paid calls erased from the audit ledger.** `record_provider_call()` only
   flushed; the background executor's `session.rollback()` on crash discarded the
   rows. This is why the 02:03:02 truncated call has no `model_invocations` row.
4. **No guard against re-resuming a deterministically failing run**, producing the
   33-resume storm that kept the WAL from checkpointing and ended in
   `database is locked`.
5. **Unreliable token estimation.** `CHARS_PER_TOKEN=2` predicted ~96 K for window
   calls that actually billed ~150 K.

## Not caused by Whole-Book V2

- **Background runtime is sound.** `whole_book_free_background.py` catches every
  exception; the sidecar survived all 36 crashes. The recurring
  `RuntimeError: no running event loop` at
  `whole_book_gateway_transport_v1.py:167` is benign `try/except` control flow in
  `_run_async`, not a defect — it appears in every traceback and has misled prior
  investigations.
- **Database growth.** 768 MB of the 963 MB database is `narrative_asset_versions`
  (4,739 rows averaging ~162 KB). Whole-Book V2's total footprint is ~9 MB.
- **Old scaffold contamination: none.** `copy_intermediates` rejects
  non-`real_provider` window assets and every run-12 asset is `origin=real_provider`.

## Fix

Per-unit **projection** (each unit receives only the topics it consumes; only
chapter-enumerating units receive the catalog), a provably convergent **bound**
(binary search over a global list cap, budgeted from the *measured* prompt
overhead rather than a nominal reserve, with `chapter_catalog` protected from
truncation), and **bounded batching** of chapter functions (40 per request,
separately checkpointed, chapter identity taken from the catalog rather than the
model because snapshots can repeat a `chapter_index`).

Measured on the 542-chapter reproduction (safe context 120,000):

| unit | before | after |
| --- | --- | --- |
| overview_type | 85,664 FAIL | 38,969 |
| story | 86,152 FAIL | 32,266 |
| characters | 87,463 FAIL | 23,828 |
| suspense | 85,124 FAIL | 12,860 |
| pacing | 85,723 FAIL | 33,333 |
| assessment | 85,914 FAIL | 40,125 |

`materialize_from_intermediates()` contains hardcoded Chinese semantics and is
deliberately **not** reused on the real-provider path; the chapter heatmap is pure
numeric aggregation over provider-authored labels.

## Test outcome

- `test_whole_book_chg086_full_production_v2_e2e.py` — 11 passed. Runs the real
  production runtime, contracts, repository, checkpoints, progress and usage
  ledger against a fake DeepSeek-shaped transport at 542 chapters / 15 windows.
  `test_synthesis_units_stay_bounded_at_production_scale` asserts each unit
  *would* have overflowed pre-fix, so the fixture cannot silently drift into
  proving nothing.
- Failure injection: provider timeout, HTTP 500, invalid JSON, truncated JSON,
  missing required field, chapter-coverage gap — paid windows retained, resume
  re-buys nothing, no duplicate successful provider units.
- CHG-086 targeted set: 89 passed. Regressions introduced by CHG-086: 11 → 0.
- Pre-existing baseline failures (identical at HEAD 7aae289, untouched): 8 —
  `chg054` ×4, `chg030` ×2, `chg061` ×1, `wb03` ×1, all
  `UNIQUE constraint failed: provider_configurations.provider_name`.

## Out of scope for this change

- `max_context_tokens=128000` for DeepSeek in `app/model_gateway/registry.py` is
  contradicted by the ledger's successful ~150 K-token calls. Raising it is a
  provider-capability claim and belongs to a separate change.
- `narrative_asset_versions` growth and WAL checkpointing belong to a separate
  database-governance change.
