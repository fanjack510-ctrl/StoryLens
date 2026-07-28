# Protected Whole-Book WIP Worktrees

Status: **PROTECTED WIP** — read-only inspection only during WB-0.x.  
Selective migration allowed only under **WB-2.1** (`CHG-20260728-018`) after independent audit.

## Forbidden operations

On these worktrees: no `reset`, `clean`, `stash`, checkout overwrite, merge, rebase, cherry-pick, delete worktree, edit any file, or copy uncommitted content directly into the v1.1.1 baseline.

## Public protected tree

| Field | Value |
|---|---|
| Path | `D:\Dstorylens-wt-narrative-phase2br1-structure-empty-policy` |
| Branch | `fix/narrative-phase2br1-structure-empty-policy` |
| HEAD | `10e69badda23c980199e9faad1ea2894a476bb86` |
| Dirty file count (at WB-0.1 freeze) | **26** |
| Status | PROTECTED WIP |

Theme: structure stages empty-policy / Public contract wiring (uncommitted).

## Private protected tree

| Field | Value |
|---|---|
| Path | `D:\Dstorylens-private-engine-wt-phase2br1-structure-empty-policy` |
| Branch | `fix/phase2br1-structure-empty-policy` |
| HEAD | `5dabfd5eb0d08e03d4fff6adb5d845a16811a39f` |
| Dirty file count (at WB-0.1 freeze) | **11** |
| Status | PROTECTED WIP |

Theme: structure citation empty-observation / coverage binding (uncommitted).  
Note: WIP HEAD is behind Private integration `30d8dad…`; future migration requires rebase plan under WB-2.1.

## Later handling

WB-2.1 must: read-only audit → selective port to `integration/whole-book-v120` → new tests → Manual Gate. Never raw copy of dirty trees.
