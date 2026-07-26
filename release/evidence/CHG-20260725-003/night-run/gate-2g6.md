# STEP 2.G6 Gate Evidence

**Change:** CHG-20260725-003  
**Step:** STEP 2.6  
**Gate:** STEP 2.G6  
**Started:** 2026-07-26T09:21:00+08:00  
**Finished:** 2026-07-26T10:05:00+08:00  
**Verdict:** PASSED

## Integration HEADs (at gate close — before STEP 2.6 commits)

| Repo | HEAD |
|------|------|
| Public | `3a21cc75f0963ed38ab3666011c0dcee654314f2` |
| Private | `48072775773a09f4dc849096ba314e4fa0487c58` |

```text
VERSION：1.0.5
Feature Flag Default：false
v1.0.5 / release/1.0.5：ddae7ee4910ab35a443e47fc1ffad4928e7a5543 (未移动)
Structure Empty Policy WIP：未触碰
Push / Tag / Release / verified：NO
Formal user DB：未访问
```

## Upgrade Fixture

| Item | Result |
|------|--------|
| Fixture | Temp SQLite (`step26_upgrade.db` / contract 1.0.5-like) |
| Path | `create_all` + `apply_narrative_migrations` ×2 |
| Before Counts | books=1 chapters=1 paragraphs=1 analysis_runs=1 reader_journey_runs=1 |
| After Counts | identical |
| Repeat Startup | PASSED (second migration no error; single `.db`) |
| New Pro tables | `whole_book_run_windows`, `whole_book_run_state_versions` present |
| Old AnalysisRun / RJ | readable (`succeeded`) |

Also: `test_minimal_1_0_5_like_upgrade_preserves_counts` PASSED.

## Import

| Format | Result | Notes |
|--------|--------|-------|
| TXT | PASSED | `test_import.py` |
| DOCX | PASSED | `test_import_docx_epub.py` (new) |
| EPUB | PASSED | `test_import_docx_epub.py` (new) |
| Original File Protection | PASSED | Fixture bytes unchanged after book DELETE |

## Free / Settings / License / Delete

| Area | Result |
|------|--------|
| Book/Chapter/Paragraph | PASSED |
| AnalysisRun | PASSED (create + read after upgrade) |
| Scene | PASSED (covered by existing Free/delete suites) |
| Reader Journey | PASSED (upgrade + delete suites) |
| Chapter Aggregation (`pro_whole_book_insights`) | PASSED (`test_pro_whole_book_insights_gate.py`) |
| Settings / Provider / Flag default false | PASSED (`test_pro_native_overview_flag.py`) |
| License / Native Overview 403 when flag off | PASSED (walking/flag suites; no Live) |
| Delete double-confirm (Desktop) | PASSED (Vitest library delete) |
| Active Whole-Book Run blocks delete | PASSED (`test_book_delete_local.py`) |
| Completed Whole-Book Run allows delete | PASSED (new STEP 2.6 case) |

## Full Test Results

| Gate | Result |
|------|--------|
| Public Full Pytest | **BASELINE_FAILURE_ONLY** — 1739 passed, 53 skipped; after phase1d fix: 19 remaining failures confirmed as pre-native (`46a2a6e` / `8abdf62^`) or CHG-002 registry |
| Private Full Pytest | **PASSED** — 200 passed |
| Desktop Vitest | **PASSED** — 140 files / 1034 tests |
| Typecheck | **PASSED** — `npm run typecheck` |
| Project Check | CHG-002 `head_inclusion` only (BASELINE; not fixed this step). Version check PASSED. CHG-003 schema/commits OK |
| Registry Check | Global FAIL = CHG-002 only. CHG-003 remains `implemented` and schema-valid |
| git diff --check (STEP 2.6 files) | PASSED |

### Baseline Failures (confirmed)

Reproduced at Public `8abdf62^` (pre native overview walking-skeleton) and/or documented prior:

1. **CHG-20260725-002 head_inclusion** — registry `check` / phase1c/2a/2b registry tests  
2. **phase2a `test_20_snapshot_missing`** — FK on `analysis_runs.book_snapshot_id`  
3. **phase2b `test_static_security_scan_paths`** — false-positive hits on `provider_execution_authorization` / dashscope host strings  
4. **phase2br `test_private_lab_router_mount_and_dry_create`** — 422 vs expected 403  
5. **phase2br1 CHG-057 / live_network / live_transport / provider_result_binding / live_engine_provenance** — `MODULE_REPAIR_EXHAUSTED` / `EXECUTION_CONTEXT_BINDING_MISSING` / `repair_exhausted` (lab Live path; failed at `46a2a6e` before native overview)

### Change-introduced (fixed this step)

- phase1d OpenAPI tests asserting POST `/whole-book-runs` absent → updated to allow native-overview-tagged POST while `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` stays True.

## Live / Cost

```text
New Live Provider Attempts：0
New Live Cost：¥0.00
Ledger Actual Cost：¥0.0958008 (unchanged from STEP 2.G5)
Ledger Reserved Cost：¥0.00
VALIDATION_MODEL_DIFFERS_FROM_PRODUCT_DEFAULT：YES (documented; product default still qwen3.7-plus)
```

## P0 / P1 / P2

```text
P0：none
P1：none open for Free/upgrade/import/delete
P2：BASELINE lab/registry failures listed above (out of STEP 2.6 Free scope; not expanded)
```

## D-Audit

```text
D-Audit：PASS

Database Upgrade：PASS
Import TXT：PASS
Import DOCX：PASS
Import EPUB：PASS
Original File Protection：PASS
Free Analysis：PASS
Reader Journey：PASS
Chapter Aggregation：PASS
Delete Protection：PASS
License：PASS
No Live API：PASS
Git Safety：PASS (VERSION 1.0.5; tags/branches unmoved; Structure WIP untouched; no Push)

允许 STEP 2.G6：YES
```

## Result

```text
STEP 2.G6 = PASSED
```

## Next Step

```text
Read STEP-2.7-DETAILED.md
Windows 1.1.0 发布候选验证
Do not Push / Tag / Release / verified
```
