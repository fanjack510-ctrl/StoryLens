# CHG-20260726-006 — 1.1.0-rc.3 candidate

```text
Status：tested (not verified)
RC2 USER ACCEPTANCE：BLOCKED (preserved)
Formal VERSION：1.0.5
```

## Installer

```text
RC Version：1.1.0-rc.3
Installer：D:\Dstorylens-wt-narrative-phase2br1-integration\dist\release\StoryLens_1.1.0-rc.3_x64-setup.exe
SHA-256：08B7E752244CC033C29299BE263DBAFB48A0C877A14B47DBA00574B44749FB76
Size：42078164
Public HEAD (tip at evidence)：a8d806d3d07e3c487456891444e7a811a05cc4ae
Feature commit：12dd3f0bd9a5f841aac7d1b3bee7860050af9710
Private HEAD：48072775773a09f4dc849096ba314e4fa0487c58
```

RC2 preserved at `dist/release/archive/StoryLens_1.1.0-rc.2_x64-setup.exe`.

## Sample estimate (1299章压力量级，非该书专用规则)

```text
character_count=2672342
estimated_windows=2046
model=qwen3.7-plus
estimated_total_tokens≈6499990
estimated_cost≈38.1658 CNY
```

## Smoke note

```text
Windows Smoke Transport = FAKE (STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE=1 available)
Real Provider Validation = USER STEP 2.8 RC3
NEW LIVE COST：¥0.00
```

## D-Audit

```text
Cloud Settings UI：PASS (cloud_enabled retained; mode coerced at runtime)
Persisted Execution Mode：PASS (stale local coerced)
Effective Mode：cloud
Single Chapter Route：PASS
Native Overview Route：PASS
Provider：aliyun_qwen_plus
Model：qwen3.7-plus (settings / BALANCED default)
Engine Metadata：private-native-overview-v1 (separate)
Token Estimate：PASS (non-zero)
Cost Estimate：PASS (non-zero when priced)
Budget Gate：existing daily budget path unchanged; zero-estimate blocks create
Task Center Error Mapping：PASS
Loading Reset：PASS (mutation onError)
No Live Cost：PASS
Database Unchanged：PASS
Contract Unchanged：PASS
Private Engine Unchanged：PASS

D-Audit：PASS
P0：none open after fix
P1：none open after fix
P2：native create_run still executes synchronously (long books may keep「启动中…」until complete/fail) — monitor in RC3 manual
允许生成 RC3：YES
```
