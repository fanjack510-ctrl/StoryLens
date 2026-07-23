# Phase 1B Canonical, Lock, and Conflict

## Canonical uniqueness

- Partial unique index: at most one `is_canonical=1` row per `asset_id` / `relation_id`
- Switch is transactional (clear old flag + set new in nested transaction)
- Rejected versions cannot become canonical

## Evidence gate

Canonical promotion requires at least one evidence row with `evidence_role=support`.  
`context` or `contradict` alone → `CANONICAL_VERSION_REQUIRED`.

When Version carries `book_snapshot_id`, evidence must use the **same** snapshot (`assert_evidence_matches_version_snapshot`).

## Lock semantics

| Actor | Locked Asset/Relation | Effect |
|-------|----------------------|--------|
| model | yes | May add candidate Version + evidence; **cannot** switch canonical |
| user | yes | May unlock then confirm/switch canonical |

Model attempt on locked identity → `AnalysisConflictSink` → `analysis_conflicts` (`LOCKED_ASSET_VS_NEW_RUN`, severity `blocking`, status stays `open`).

User-protected canonical (confirmed/corrected) blocks model replacement → `DUPLICATE_ASSET_CANDIDATE` conflict (Asset path).

## Conflict sink (cycle-free)

```
NarrativeAssetService ──► AnalysisConflictSink (Protocol)
                              └── AnalysisConflictSinkImpl
                                      └── AnalysisConflictServiceImpl
```

Asset/Relation services never import each other's repositories for conflict persistence.

## Cross-book guard

`AnalysisConflictServiceImpl` resolves `book_id` from both refs; mismatch → `CONFLICT_CROSS_BOOK`.
