# STEP 2.G6 Free Entitlement Supplement

**Change:** CHG-20260726-004  
**Gate:** Free Entitlement Supplement to STEP 2.G6  
**Started:** 2026-07-26T10:20:00+08:00  
**Finished:** 2026-07-26T10:40:00+08:00  
**Verdict:** PASSED

```text
Supplement Public HEAD (after CHG-004 commits)：
50058fe13c2c154d2edd7aeb650203ba61bdfe67

Private HEAD (unchanged)：
48072775773a09f4dc849096ba314e4fa0487c58
```

## Original Gate (unchanged historical evidence)

```text
Original Gate：
release/evidence/CHG-20260725-003/night-run/gate-2g6.md

Original Public HEAD：
4d7189ebca505f9168487602efbbf7877c167173

Original Private HEAD：
48072775773a09f4dc849096ba314e4fa0487c58

ORIGINAL STEP 2.G6：
PASSED
```

That file remains the record that STEP 2.G6 passed under the **previous Pro entitlement standard**.  
It must not be rewritten. Counts / import / upgrade / Desktop / Private / cost evidence there stay valid.

## Product decision applied by CHG-004

```text
Native Whole-Book Overview → FREE (StoryLens 1.1.x)
Private Native Overview Engine → CLOSED SOURCE
Pro product start → 1.2.0
Feature Flag key → PRO_NATIVE_OVERVIEW_ENABLED (unchanged; default false)
```

## Supplement checks

| Check | Result |
|-------|--------|
| Free Native Preflight allowed | PASSED |
| Free Native Create Run allowed | PASSED |
| Free Native Get Run / Overview allowed | PASSED |
| Native Overview does not return `PRO_LICENSE_REQUIRED` | PASSED |
| Feature Flag false still denies | PASSED (walking skeleton) |
| Future Pro capability (`pro_whole_book_insights`) still denied without license | PASSED |
| Enhanced mode still license-gated via CapabilityService | PASSED |
| `PRO_LICENSE_REQUIRED` error code retained | PASSED |
| UI label「原生全书概览」; no Pro paywall | PASSED |
| Third-party API cost notice in consent | PASSED |
| 章节聚合洞察 entry/name unchanged | PASSED |
| Router / Book Workspace smoke | PASSED |
| Database / Migration / API / Route / DTO / Contract / Fixture hash | UNCHANGED |
| Private Engine ID / no license dependency | PASSED (directed Private tests; no license checks in engine) |
| Live Provider | NO (¥0 new) |
| VERSION | 1.0.5 |
| Feature Flag default | false |

## Directed test commands

```text
Public backend (Private PYTHONPATH):
pytest test_native_overview_free_entitlement + walking_skeleton + flag + insights gate + pro_license_local
→ 39 passed

Public frontend:
vitest proNativeOverview + router.smoke + wholeBookInsights
→ 24 passed
npm run typecheck → PASSED

Private directed:
pytest native_overview_engine + fixture_adapter + contract
→ 38 passed
```

## Compatibility

```text
Database Changed：NO
Migration Changed：NO
API Changed：NO
Route Changed：NO
DTO Changed：NO
Contract Changed：NO
Fixture Hash Changed：NO
Private Engine Contract/ID Changed：NO
```

## D-Audit (supplement)

```text
D-Audit：PASS

Free Native Overview：PASS
Private Engine Boundary：PASS
License Policy：PASS (native Free; future Pro still gated)
Capability Registry：PASS (legacy key kept; docs note Free native)
UI Semantics：PASS
Documentation：PASS (scope/roadmap/architecture + STEP 2.6/2.7 DETAILED amended)
Compatibility：PASS

P0：none
P1：none
P2：optional neutral capability alias before 1.2.0 (not in this change)

Allow EFFECTIVE STEP 2.G6 under CHG-004：YES
```

## Result

```text
ORIGINAL STEP 2.G6：PASSED
FREE ENTITLEMENT SUPPLEMENT：PASSED
EFFECTIVE STEP 2.G6：PASSED UNDER CHG-20260726-004
```

## Next

```text
STEP 2.7 must use STEP-2.7-DETAILED.md amended by CHG-20260726-004
Do not auto-start Windows build / Push / Tag / Release / verified
```
