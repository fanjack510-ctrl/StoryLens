# Phase 2A Run Actions Contract

## Pause

Cooperative; checkpoint; return requested/accepted/current_state; keep results.

## Resume

paused/interrupted; skip completed stages; restore checkpoint; same run_id.

## Retry

Failed stage; validate downstream; reset affected downstream; bump attempt_count; keep historical artifacts; new artifact uses new attempt.

## Cancel

Secondary confirm; cooperative; safe stop; retain candidates; cancelled terminal; do not delete Snapshot/Book/user files.
