# Phase 1D Agent J — Module Selection UX

## Frozen modules (11)

`book_overview`, `structure_stages`, `chapter_functions`, `storylines`, `characters`, `character_arcs`, `relationships`, `hooks_payoffs`, `causal_chain`, `basic_timeline`, `diagnostics`

## Rules implemented

1. Formal Module Keys only (display names are labels).
2. User checks modules → UI shows `resolved_modules`.
3. Auto-filled modules (resolved − requested) marked **自动依赖** and cannot be unchecked.
4. Module ≠ Stage: separate “resolved stages” panel using shared `resolveModulesWithDependencies` / `MODULE_STAGE_DEPENDENCIES`.
5. No second dependency graph inside the component.
6. `diagnostics` shows explicit high-dependency hint.
7. No real prices / commercial quotas in this prototype.

## Stage plan preview

Consumes backend/fixture `stage_plan` rows:

- `stage_key`, `display_name`, `order`, `required`, `resumable`, `retryable`, `dependencies`, `estimated_cost_class`, `produced_module_keys`
- Auto-filled stages visually dashed / chip **自动补齐**
- No prompts / model params / credentials / fake token counts
- Cost/duration marked as 估算
