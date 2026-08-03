# REGISTRY_DIFF — CHG-20260803-044

Machine-readable companion: `REGISTRY_DIFF.json`（由 apply 脚本生成）。

## Top-level additions

- `v120_scope_reconciliation`
- `v120_free_product_scope`
- `v120_free_release_path`
- `v120_release_steps`（3 个发布子步；**不**计入冻结的 37 历史编号步）

## Historical `steps[]` count

- Before: **37**
- After: **37**（不删除历史步骤）

## Critical field changes

| Step | Field | Before | After |
|---|---|---|---|
| WB-2.2-CHAPTER-FUNCTIONS | next_step | WB-2.3-STORYLINES | **WB-2.2.1-V120-E2E-STABILIZATION** |
| WB-2.2 | scope_disposition | (none) | feature_complete |
| WB-2.3-STORYLINES | scope_disposition | (none) | **deferred** / pro_future / not required |
| WB-2.4-FIRST-FOUR-PRODUCT | scope_disposition | (none) | **superseded_by_current_free_four_modules** |
| WB-3.1…WB-5.4 | scope_disposition | (none) | **out_of_scope_for_1.2.0** |
| WB-6.1…WB-6.3 | scope_disposition | (none) | **out_of_scope_for_1.2.0_free_release** |
| WB-6.4-120-RC | depends_on | WB-6.3-COST-QUOTA-PRODUCT | **WB-2.2.3-V120-L3-PROVIDER**（legacy_depends_on 保留旧值） |
| WB-6.4 / WB-6.5 | v120_required | (none) | true |

## branch_strategy

- Retains historical `integration/whole-book-v120`
- Adds active: `integration/1.2.0-after-1.1.2`

## Verifier

`scripts/verify_whole_book_execution_registry.py` continues to enforce **37** historical numbered steps; additionally checks presence of `v120_free_release_path` / `v120_release_steps` when present.

V120 path checks: **PRESENT_OK** after CHG-044.

Pre-existing unrelated FAIL (unchanged by this Change; do not rewrite history):
four short `evidence_dir` values `WB-0.2/` … `WB-0.5/` that never matched the full `WB-X.Y-NAME/` pattern. Not introduced by CHG-044.
