# Phase 2B Evidence Coverage

## EvidenceCoverageCalculator

Outputs: total_claims · claims_with_support · claims_with_contradiction · claims_with_context · unsupported_claims · invalid_evidence · duplicate_evidence · coverage_ratio · critical_coverage_ratio · accepted

## EvidencePolicy (versioned)

Keys: `evidence.minimal` · `evidence.standard` · `evidence.strict`  
Version: `1.0.0`

## Rules

1. Critical claims configurable via policy / claim flag
2. Unsupported critical claims → not `accepted`
3. Coverage ≠ quality score
4. Thresholds are generic policy values — never single-book hardcodes
5. Modules may select different policy keys
6. Contradictory evidence listed in report / explanation
7. Never forges 100% coverage
