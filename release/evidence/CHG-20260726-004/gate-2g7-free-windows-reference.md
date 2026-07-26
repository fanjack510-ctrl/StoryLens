# CHG-20260726-004 — STEP 2.G7 Free Windows Reference

Primary G7 evidence lives under CHG-003:

```text
release/evidence/CHG-20260725-003/night-run/gate-2g7.md
release/evidence/CHG-20260725-003/night-run/windows-rc-2g7-smoke.json
release/evidence/CHG-20260725-003/night-run/windows-build-log.md
```

## CHG-004 scope confirmed on Windows RC

```text
Native Overview Free Entitlement：PASS (no VIP; no PRO_LICENSE_REQUIRED)
UI product semantics：PASS (preflight engine_id=private-native-overview-v1; frontend create binding defaults Private)
Free Windows Smoke：PASS (isolated sidecar + Fake transport)
Future Pro Gate：PASS (directed pytest; Enhanced / Pro insights still license-gated)
Closed Source Engine boundary：PASS (Private packaged + loaded; no silent Fixture default)
```

```text
Windows Smoke Transport = FAKE
Live Provider Evidence = STEP 2.G5
New Live Cost = ¥0.00
```
