# FAILURE_CLASSIFICATION — CHG-20260803-049

Scope: one Public full pytest + one Desktop full Vitest + check_project + typecheck + production build + registry/version/migration snapshots. No product code fixes in this CHG.

## Suite totals
| Suite | Result |
|---|---|
| Public pytest | **40 failed**, 2136 passed, 54 skipped, **6 errors**, 1170s |
| Desktop Vitest | **30 failed**, 1392 passed, 111s |
| check_project | **FAIL** at `change_registry.py check` (~143s; not TIMEOUT) |
| Typecheck | **PASS** |
| Desktop production build | **PASS** |
| version_manager check | **PASS** (1.2.0) |
| change_registry check | **FAIL** (see CHANGE_REGISTRY_CHECK.txt) |

## RELEASE_BLOCKING_PRODUCT
| ID | Item | Evidence | Why blocking |
|---|---|---|---|
| P1 | Scene fake-provider complete pipeline progress mismatch | `test_scene_pipeline.py::test_fake_provider_complete_pipeline` → `progress_current(3) != progress_total(1)` while `status=succeeded` | Scene main-chain progress shown to users is wrong even when run succeeds |
| P2 | CHG-041 scene-boundary-review navigation mapping | Vitest `SceneBoundaryNavigation.chg041.test.tsx` → expected view `scene`, got `journey` | Scene-boundary review entry routing regression risk on shipped UI |

## RELEASE_BLOCKING_TOOLING
| ID | Item | Evidence |
|---|---|---|
| T1 | VERSION vs release baseline/unreleased pin | VERSION/package/tauri=`1.2.0` but `release/baseline.json` & `unreleased.base_version` still `1.0.5` |
| T2 | Change Registry schema/status/head_inclusion/unregistered commits | `CHANGE_REGISTRY_CHECK.txt` / check_project FAIL |
| T3 | check_project gate FAIL | Fails immediately after version check at change_registry step |
| T4 | native_overview pytest plugin ImportError (×3 collection errors) | `pytest_plugins=["test_native_overview_walking_skeleton"]` → module not found |
| T5 | phase2br1 http_replay sibling ImportError (×3 collection errors) | `from test_narrative_phase2br1_http_replay_no_repair import …` ModuleNotFoundError |

## OBSOLETE_TEST
| ID | Item | Evidence |
|---|---|---|
| O1 | 1.0.5 version locks | e.g. `test_version_is_1_0_5`, phase2br/phase2br1 `test_*version*`, gate locks asserting VERSION==1.0.5 |
| O2 | Migration order length locks | actual `len(NARRATIVE_MIGRATION_ORDER)==16`; tests still assert 13/14 (`test_migration_order_includes_011`, phase1bp/1p unique/order) |
| O3 | Capability/gate “not shipped / preview_visible / frozen” locks | e.g. `test_01_capability_not_shipped_preview_visible` (preview_visible False), phase2br gate-frozen suites |
| O4 | Reader Journey v2 wiring mocks | `test_execute_reader_journey_*` SimpleNamespace missing `analysis_run_id` |
| O5 | Pro whole-book insights display_name copy lock | `test_capability_key_and_aggregation_semantics_unchanged` |
| O6 | snapshot_missing recovery fixture vs FK | `test_20_snapshot_missing` IntegrityError on invalid `book_snapshot_id` |
| O7 | Desktop readerJourney IA/copy/CSS locks (majority of 30 fails) | missing `scene-detail-tabs/*`, old metric labels, CSS selector locks, dimension copy, recovery card testid |
| O8 | Related desktop non-RJ obsolete expectations | `ChapterAnalysisProgressPanel` unified-recovery-card; `dimension_insights_chg001_local`; `runtime_capabilities_local` brand; parts of `BookRoutePage.autoDiscover` |

## ENVIRONMENT_ONLY
| ID | Item | Notes |
|---|---|---|
| E1 | *(none confirmed as sole root cause of a failing case)* | soupsieve warning only; collection ImportErrors classified as tooling/harness (T4/T5), not machine path drift |

## FORMAL_EXCEPTION_CANDIDATE
| ID | Item | Notes |
|---|---|---|
| X1 | Reader offset highlight enhancement | Deferred desktop polish; production evidence contract already PASS in CHG-048 |
| X2 | DEV diagnostics fuzzy cleanup | DEV-only; does not affect production drawer contract |

## UNKNOWN (default blocking until investigated)
| ID | Item | Notes |
|---|---|---|
| U1 | phase2br1 live / transport / provider-binding / chg057 acceptance (multiple) | Need per-test triage: private-lab harness vs product regression |
| U2 | `test_phase_1c_a10::test_partial_success_then_resume_skips_completed` | Resume semantics unclear without deeper log |
| U3 | `test_provider_health_consistency_chg009::test_incident_db_replay_becomes_fresh` | Insufficient failure detail in full -q log |
| U4 | `test_narrative_phase2b_integration::test_static_security_scan_paths` | May be path lock or real scan debt |
| U5 | `test_create_all_on_empty_temp_db` / remaining migration idempotent fails beyond count locks | Confirm whether DDL body vs assertion only |

## Deferred investigations (explicitly not auto-blocking)
- Reader offset highlight enhancement → X1
- DEV diagnostics fuzzy cleanup → X2
