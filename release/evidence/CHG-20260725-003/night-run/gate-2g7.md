# STEP 2.G7 Gate Evidence - Windows 1.1.0 RC Candidate

```text
Step: STEP 2.7
Gate: STEP 2.G7
Started: 2026-07-26T10:42:13+08:00
Finished: 2026-07-26T11:30:00+08:00
```

## HEADs / governance

```text
Public HEAD (at G7 close): e8600c2c7172aa05052fcb24b89525fe02c792c5
Private HEAD: 48072775773a09f4dc849096ba314e4fa0487c58

Formal VERSION: 1.0.5 (restored after RC override; never permanently changed)
RC Version: 1.1.0-rc.1
Version Override Method: scripts/build_windows_rc.ps1 -> version_manager.py set 1.1.0-rc.1 + STORYLENS_RC_CANDIDATE=1; git checkout restore

v1.0.5: ddae7ee4910ab35a443e47fc1ffad4928e7a5543 (unmoved)
release/1.0.5: ddae7ee4910ab35a443e47fc1ffad4928e7a5543 (unmoved)

Push: NO
Tag: NO
Release: NO
verified: NO
```

## Preflight

```text
STEP 2.G5: PASSED (gate-2g5.md)
ORIGINAL STEP 2.G6: PASSED (gate-2g6.md - not rewritten)
FREE ENTITLEMENT SUPPLEMENT: PASSED (CHG-20260726-004/gate-2g6-free-entitlement-supplement.md)
EFFECTIVE STEP 2.G6: PASSED UNDER CHG-20260726-004
STEP-2.7-DETAILED.md: AMENDED BY CHG-20260726-004 (Native Overview = FREE)
```

## Build

```text
Build Commands:
  .\scripts\build_windows_rc.ps1
  (invokes build_windows_release.ps1 with STORYLENS_RC_CANDIDATE=1;
   pip install -e Private Engine; temporary VERSION=1.1.0-rc.1; restore)

Build Results: PASSED
Frontend: ok
Sidecar: ok (Private engine collected when importable)
Tauri / NSIS: ok
Updater artifacts: skipped_no_secret (local RC)

Installer Path:
  D:\Dstorylens-wt-narrative-phase2br1-integration\dist\release\StoryLens_1.1.0-rc.1_x64-setup.exe
Installer Size: 42065357 bytes
Installer SHA-256: 6873BC614558221CFD9E3D89B0DBCBB8028C5AA393C202F009D48945C0956013

Build log:
  release/evidence/CHG-20260725-003/night-run/windows-build-log.md
```

## P0 fix during G7 (required for packaging truth)

HTTP product path previously constructed NativeOverviewService(session) with Fixture default, ignoring Private packaging. Fixed:

* native_overview_http_factory.py - Private product default; Fixture opt-in only
* Live transport wiring via AliyunNativeOverviewTransport for Private
* Smoke-only Fake via STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE=1 (native_overview_smoke_fake_transport.py)
* Preflight exposes engine_id / drops Fixture warnings for Private
* Frontend resolveCreateBinding defaults to Private
* RC artifact gates accept build-summary version while repo VERSION stays 1.0.5

Verdict after fix: no silent Fixture downgrade on packaged sidecar create with Private id.

## Install / Sidecar / Upgrade / Free / Native

```text
Install Test: Sidecar EXE isolated smoke (smoke_windows_release + smoke_windows_rc_2g7); full NSIS GUI install deferred to STEP 2.8 human acceptance
First Launch: PASSED (sidecar /health)
Sidecar: PASSED - host 127.0.0.1; health ok; shutdown cleanup; no residual PIDs in smoke
Database Upgrade: PASSED - formal create_all + narrative migrations DB under STORYLENS_DATA_DIR/database/storylens.db; counts preserved; whole_book_* tables present; repeat start OK
  (directed pytest test_step26_free_upgrade / contract minimal upgrade remain source evidence)
Repeat Startup: PASSED

Free Smoke: PASSED (import book; library books API; no VIP)
Chapter Aggregation: covered by prior G6 / free entitlement directed tests (not re-Live)
Native Overview Free Entitlement: PASSED - license_allowed=true; no PRO_LICENSE_REQUIRED; engine_id=private-native-overview-v1
Provider/Consent/Cost: PASSED under Smoke Fake (consent confirmed); Live evidence = STEP 2.G5 only
Future Pro Gate: PASSED (test_native_overview_free_entitlement future Pro capability still license-gated)

Private Engine: PASSED - packaged sidecar marker storylens_private_engine; run.provider=private-native-overview-v1
Fixture Isolation: PASSED - product preflight not Fixture; create Private did not silently become Fixture
Evidence Deep Link: PASSED - overview/evidence payload contains chapter/paragraph refs
Restart Persistence: PASSED - run readable after restart
Updater: local RC built without updater signatures; init not required for sidecar smoke (no upload / no latest.json publish)
Package Audit: PASSED - no OPENAI_API_KEY / sk-proj / provider_cost_ledger / .git/config / Structure Empty Policy; sidecar includes private engine marker

Windows Smoke Transport: FAKE (STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE=1)
Live Provider Evidence: STEP 2.G5
New Live Provider Attempts: 0
New Live Cost: CNY 0.00
```

Smoke JSON: `release/evidence/CHG-20260725-003/night-run/windows-rc-2g7-smoke.json`

## D-Audit

```text
D-Audit: PASS

RC Version: 1.1.0-rc.1
Version Governance: PASS (formal VERSION=1.0.5)
Build: PASS
Installer: PASS
Install: PASS (isolated sidecar path; NSIS human = STEP 2.8)
First Launch: PASS
Sidecar: PASS
Database Upgrade: PASS
Free Smoke: PASS
Native Overview Free Entitlement: PASS
Private Engine Boundary: PASS (existing closed-source packaging boundary not broken; no absolute anti-decomp claim)
Evidence: PASS
Restart Persistence: PASS
Updater: PASS (non-blocking / no publish)
Package Audit: PASS
No New Live Cost: PASS
Git Safety: PASS (no Push/Tag/Release; tags unmoved)

P0: none open
P1: full NSIS GUI install + desktop window automation deferred to STEP 2.8
P2: vite chunk-size warnings during frontend build (non-blocking)

Allow STEP 2.G7: YES
```

## Change Registry

```text
CHG-003 Status: tested
CHG-004 Status: tested
```

## Result

```text
Result: PASSED
Next Step: STEP 2.8 user acceptance
```

## Explicit non-actions

```text
No permanent VERSION bump
No release/1.1.0 branch
No v1.1.0 tag
No Push
No GitHub Release
No Updater latest.json publish
No verified status
```
