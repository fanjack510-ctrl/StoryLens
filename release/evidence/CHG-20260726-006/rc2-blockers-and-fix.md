# CHG-20260726-006 — RC2 blockers and FIX-2

```text
Status：implemented (pending RC3 tested)
RC2 USER ACCEPTANCE：BLOCKED
Target candidate：1.1.0-rc.3
```

## Root cause

```text
1. CLOUD_MODE_REQUIRED
   Chapter create validated raw request.execution_mode against cloud providers.
   Schema default / stale developer-local mode stayed "local" while settings showed
   Aliyun READY + cloud_enabled. Analysis profile「均衡」is unrelated to routing.

2. Native preflight zeros + Engine/Provider mix-up
   native_overview_service.preflight hard-coded estimated_tokens/cost = 0 and set
   provider_id/model_id = engine identity (private-native-overview-v1).

3. Task Center offline copy
   ErrorState always showed error.message; network copy dominated UX.
   422 business failures must keep business codes (mapTaskCenterError).
```

## Fix summary

```text
- resolve_effective_execution_mode (+ coerce on chapter create)
- native_overview_ai_binding + estimate_native_overview_usage
- Preflight UI: Engine / Provider / Model / Free entitlement / 云端
- taskCenterErrors mapper + TasksPage classifyTaskErrors
- StartAnalysisDialog: coerce cloud provider away from local; CLOUD_MODE copy;
  network detection via ApiError.status
```

## Local verification

```text
pytest execution_mode + ai_binding + walking + free：30 passed
vitest taskCenterErrors + proNativeOverview：20 passed
typecheck：pass
git diff --check：pass
NEW LIVE COST：¥0.00
```
