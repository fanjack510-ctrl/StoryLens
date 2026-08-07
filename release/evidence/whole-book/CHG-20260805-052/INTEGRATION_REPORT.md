# CHG-20260805-052 — V1.2.0 Release Debt Integration Report

CHANGE：CHG-20260805-052  
WB STEP：WB-2.2.2-V120-RELEASE-DEBT  
Date：2026-08-07

## Merges

| Step | Commit | Conflicts |
|---|---|---|
| Base | `d5cb364667a298538cc545f742197a17056a90ce` | clean (restored CRLF dirty on CHG-029) |
| Agent1 merge | `466107e94933bb81291fc97ce1272475b2fe7b2c` | 0 |
| Agent2 merge | `73ec5ba9c0b2439a4a2599b47a49bf102ef76cbe` | 0 |

CONFLICT FILE COUNT：0

## Directed smoke

| Gate | Result |
|---|---|
| Scene progress | PASS |
| version_manager | PASS |
| change_registry (after CHG-051/052 register) | PASS |
| migration | PASS (33) |
| native_overview collection | PASS (25 collected) |
| http_replay collection | PASS (7 collected) |
| SceneBoundaryNavigation | PASS (4 files / 34) |
| Evidence/restore | PASS (3 files / 44) |
| readerJourney core | PASS (63 files / 499) |

## Full gates (one run each)

| Gate | Result |
|---|---|
| Public full pytest | **FAIL** — 11 failed, 2184 passed, 54 skipped, 0 collection errors, 919s |
| Desktop full Vitest | PASS — 187 files / 1422 tests, 139s |
| check_project | PASS |
| version_manager | PASS |
| change_registry | PASS |
| typecheck | PASS |
| desktop production build | PASS (INDEX_NO_DEV=True, JS_DEV_ROUTE_HITS=0) |

## Remaining failures classification

All 11 failures are U1 phase2br1 private-lab / live / chg057 / provider-binding suite.

**Class：LAB_DEBT**

Premise check：`is_private_engine_lab_enabled_from_env(environ={}) is False` — not loaded by V1.2.0 Free formal entry.

X1 Reader offset highlight / X2 DEV diagnostics fuzzy：**DEFERRED_NON_BLOCKING** (not implemented; production contract unaffected).

Formal exceptions：**not approved** — awaiting product owner.

## Status decision

Because Public full pytest numeric gate is not 0-failed, Release Debt Gate is **blocked** pending LAB_DEBT formal exception or lab-suite quarantine.

CHG-050 / CHG-051 remain **tested** (not verified).  
CHG-052 / WB-2.2.2：**blocked** (report); registry JSON status stays `tested` (no `blocked` enum).

READY FOR REAL PROVIDER L3：**NO**

NEXT：FIX RELEASE BLOCKER (formal-exception / LAB_DEBT quarantine) before WB-2.2.3
