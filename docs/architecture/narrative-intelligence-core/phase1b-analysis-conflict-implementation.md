# Phase 1B — Analysis Conflict Implementation (Agent F)

**Change:** CHG-20260723-019  
**Owner:** Agent F  
**Migration:** `20260723_010_analysis_conflicts`  
**Table:** `analysis_conflicts`

## Purpose

Persist analysis disagreements without auto-adjudication. Blocking conflicts stay `open` until an explicit user/system close.

## Fields

| Field | Notes |
|-------|-------|
| `conflict_type` | Locked vs run, candidate contradiction, entity identity, relation conflict, evidence stale, snapshot mismatch, duplicate asset candidate |
| `left_ref_type` / `left_ref_id` | Polymorphic ref |
| `right_ref_type` / `right_ref_id` | Polymorphic ref |
| `severity` | `info` \| `warning` \| `blocking` |
| `status` | `open` → `resolved` \| `dismissed` (terminal) |
| `resolution_json` | Must include `schema` + `version` |
| `resolved_by` / `resolved_at` | Set on close |

## Lifecycle

1. `create_analysis_conflict` → `open`
2. `resolve_analysis_conflict` / `dismiss_analysis_conflict` → terminal
3. Re-close raises `CONFLICT_ALREADY_CLOSED`
4. Rows are never physically deleted
5. Descriptions are truncated; full user body text must not be stored

## Minimal request interface (no Relation cycle)

Agent E / Integration may import:

```python
from app.narrative_core.services.conflict_service import (
    ConflictCreateRequest,
    AnalysisConflictServiceImpl,
)
```

`ConflictCreateRequest` is a frozen dataclass; `create_from_request` avoids importing Relation services.

## Relation integration

Locked Relation + model canonical attempt records a `relation_conflict` / blocking Conflict before raising `RELATION_LOCKED`.
