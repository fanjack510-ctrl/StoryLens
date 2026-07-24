# Phase 2B Hierarchical Context Planner

## HierarchicalContextPlanner

Levels:

| Level | Content |
|-------|---------|
| 0 | Book metadata + chapter TOC units |
| 1 | Chapter refs (+ derived summary refs) |
| 2 | Scene / paragraph group |
| 3 | Evidence window |

## Behavior

1. Required levels come from Module Execution Spec.
2. Token budget = provider context limit × budget policy fraction (`tight`/`standard`/`relaxed`).
3. Evidence (Level 3) preferred over unconstrained Level 2 dumps under tight budget.
4. Over-limit → stable downgrade warnings or `CONTEXT_LIMIT_EXCEEDED`.
5. No Prompt writing; no model calls; no per-book thresholds.
