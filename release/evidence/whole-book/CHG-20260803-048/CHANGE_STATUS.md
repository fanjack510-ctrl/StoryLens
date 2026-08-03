# CHANGE_STATUS — CHG-20260803-048 / agents

| Change | Role | Status | Notes |
|---|---|---|---|
| CHG-20260803-045 | Planning parent | planning / prior | Scope freeze for WB-2.2.1 |
| CHG-20260803-046 | Agent 1 backend | **tested** | Merged as `18c79e1`; not verified |
| CHG-20260803-047 | Agent 2 desktop | **tested** | Merged as `de417b4`; not verified |
| CHG-20260803-048 | Integration | **tested** | This evidence pack; MG pending |
| WB-2.2.1 | Step | **tested** | Do not mark verified until MG-V1.2.0-E2E-STABILIZATION PASS |

## ID collision (do not start WB-2.2.2)
Historically planned `v120_release_steps` labels reused `CHG-20260803-046` / `047` for WB-2.2.2 / WB-2.2.3. Agent E2E work now owns those IDs as **tested** agent changes. Reassign future step change_ids only when starting WB-2.2.2 planning — **not in this wave**.
