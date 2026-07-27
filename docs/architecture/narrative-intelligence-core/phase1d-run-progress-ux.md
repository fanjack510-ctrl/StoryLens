# Phase 1D Agent J — Run Progress UX

## View state

Consumes `WholeBookRunViewState` fixtures (`runViewFixtures.ts`):

running / paused / interrupted / failed / completed / cancelled

Displays:

- Aggregate status (text + `data-status`, not color-only)
- Current stage, stage list, completed / available / failed modules
- Partial results notice
- Token/cost summary (honest nulls allowed)
- started_at / updated_at
- blocking_issue
- `allowed_actions` (fixture/backend authored)

## Distinctions

| Pair | Rule |
|------|------|
| paused vs failed | Separate status + labels |
| interrupted vs failed | Separate `data-interrupted` / `data-failed` |
| partial results | Explicit notice; completed modules survive later failure |
| cancelled | Candidates retained; not delete book/snapshot |

## Controls (Mock only)

`mockRunActionAdapter`:

| Action | Gate | Behavior |
|--------|------|----------|
| pause | `allowed_actions` has pause | → paused; completed untouched |
| resume | paused/interrupted + allowed | completed stages not re-run |
| retry | failed stage + allowed | increments attempt; downstream may invalidate |
| cancel | double confirm | retains candidates |

Future API request JSON is previewed in UI; **no production run control HTTP**.

## Honesty

- No fake remaining time
- No blinking progress animation
- Progress percent may be null → show stage status instead
