# Phase 2B Native / Enhanced Context Providers

## NativeWholeBookContextProvider

- Depends on completed Snapshot only
- Does not require Scene / Reader Journey / chapter assets
- Bundle `mode=native`
- Evidence still bound to Snapshot paragraph hashes
- No real literary conclusions; no model calls

## EnhancedWholeBookContextProvider

- Snapshot remains first fact source
- May read Scene / Reader Journey / chapter analysis assets (same Book)
- Snapshot mismatch → `stale` warnings
- Missing aux → degrade + warnings (does not fail)
- Rejected asset versions excluded
- Candidate vs canonical labeled in coverage notes
- Aux assets never become final original-text Evidence and never override Snapshot
- Does not auto-confirm assets; no model calls
