# CHG-20260731-029 Conflict Resolution

## Summary
Public `git merge --no-ff v1.1.2` into Wave D base `e35bc99`.

Conflict file count: **1**

## Conflicts

### 1. `release/unreleased.json`

| Field | Detail |
| --- | --- |
| v1.1.2 side | Appends hotfix train CHGs (`CHG-20260729-008` … `CHG-20260731-027`) |
| Wave D side | Appends whole-book Wave A–D CHGs (`CHG-20260728-001` … `CHG-20260728-039`) |
| Resolution | Union both lists (stable order: shared prefix → Wave D CHGs → v1.1.2 CHGs) + add `CHG-20260731-029`; set `target_version` to `1.2.0` |
| Hand rewrite | Yes (JSON union; no ours/theirs wholesale) |
| Tests | `scripts/change_registry.py check` |
| Contract impact | Registry only; no Public/Private runtime contract change |

## Auto-merged overlapping paths (no conflict markers)

### `apps/api/app/db/models.py`
- Both sides extended models; Git auto-merged without markers.
- Keep both Wave D whole-book tables and v1.1.2 hotfix model fields.

### `apps/api/app/main.py`
- Auto-merged router registration.
- Must retain Wave D whole-book routers and v1.1.2 journey/scene routes.

### `apps/desktop/src/pages/BookRoutePage.tsx`
- Auto-merged.
- Verified post-merge: imports `WholeBookFreeEntry` and Journey/scene recovery UI coexist (`WholeBookFreeEntry` around toolbar; Journey progress/result components retained).
- Must **not** replace Wave D whole-book page with old 1.1.2-only book page.

## Non-conflicts of note
- Wave D Free product pages/APIs remain present.
- v1.1.2 Journey CTA / resume / cancel evidence and code entered via merge of tag `v1.1.2`.

## Version correction after merge
Tag `v1.1.2` brought `VERSION`/`package.json`/`tauri.conf.json` to `1.1.2`. Corrected to **1.2.0** before merge commit finalization.
