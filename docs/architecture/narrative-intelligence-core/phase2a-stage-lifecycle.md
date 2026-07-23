# Phase 2A Stage Lifecycle

Reuse Phase 1A transitions + Phase 1C 10 stages:

build_fulltext_index → resolve_entities → analyze_structure → analyze_storylines → analyze_characters → analyze_hooks → analyze_causality_timeline → generate_diagnostics → verify_evidence → persist_narrative_assets

## Rules

1. dependency order
2. completed stages not re-run
3. skipped needs reason
4. pause saves checkpoint
5. interrupt saves last checkpoint
6. retry bumps attempt_count
7. failed retry resets self + affected downstream only
8. cancel checked around stage
9. BudgetGuard before writes
10. WholeBookStageArtifactEnvelope per stage
11. artifacts mock/synthetic/non-production
12. candidates only
13. no auto confirm
14. no auto lock
15. no canonical overwrite
