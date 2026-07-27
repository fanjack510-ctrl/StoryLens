# Phase 2B Evaluation Contract

Types: `WholeBookEvaluationSuite`, `WholeBookEvaluationCase`, `WholeBookEvaluationResult`, `MetamorphicEvaluationCase`.

Phase 2B-P: fixtures + Fake results + harness only. **Synthetic samples only** — no copyrighted full novels.

## Sample categories

Linear long-form · multi-thread parallel · multi-viewpoint · flashback/inset · short story · ultra-long chapter · side story · missing chapters · duplicate chapters · garbled/degraded text · Chinese · English · mixed language

## Dimensions

Schema validity · Snapshot integrity · Evidence integrity · Evidence coverage · Reference validity · Book isolation · Module completeness · Contradiction rate · Duplicate rate · Cross-run stability · Partial recovery · Cost/Token · Latency · User correction rate

## Metamorphic tests (minimum)

- Slight chapter-title change
- Whitespace/newline change
- Chapter renumbering with unchanged content
- Irrelevant preface added
- Synonym-rewritten summary does not affect original Evidence
- Enhanced aux assets missing → degrade
- Module order change
- Resume does not duplicate prior outputs
