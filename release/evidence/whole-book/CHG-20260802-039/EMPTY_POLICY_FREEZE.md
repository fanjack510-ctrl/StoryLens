# CHAPTER FUNCTIONS EMPTY / INSUFFICIENT POLICY FREEZE

**Status:** FROZEN for WB-2.2  
**Novel-specific thresholds:** FORBIDDEN  
**Pattern:** Mirror WB-2.1 EMPTY_POLICY_FREEZE semantics with chapter-function codes.

## 1. Legal completed non-empty

When server-frozen `expected_coverage_scope != insufficient`:

| Rule | Freeze |
|---|---|
| `chapters` count | **≥ 1** |
| Each item | `chapter_id`, `chapter_order`, `confidence`, controlled labels fields |
| Claims | observed/inferred require non-empty value + ≥1 catalog citation |
| Forced taxonomy templates | Forbidden |
| `coverage_scope` | Must equal server-frozen expected exactly |

## 2. Legal empty / insufficient

Allowed **only** when:

```
coverage_scope = insufficient
chapters = []
```

AND binding `permits_empty_observation=true`（no usable chapter units / catalog）.

Capability true + empty `chapters` → **illegal**（max-1 repair, then fail-closed）.

### Failure codes（freeze names）

| Code | Meaning |
|---|---|
| `CHAPTER_FN_COVERAGE_SCOPE_BINDING_MISMATCH` | scope ≠ expected / empty rules broken |
| `CHAPTER_FN_REQUIRED_CHAPTER_MISSING` | observation required but chapters empty |
| `CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR` | still illegal after repair |
| `CHAPTER_FN_CONTRACT_FAILURE` | generic contract envelope |
| `CHAPTER_FN_LABEL_UNKNOWN` | label outside controlled set |
| `CHAPTER_FN_PRIMARY_SECONDARY_CONFLICT` | illegal primary/secondary shape |
| `CHAPTER_FN_CITATION_EMPTY` | required claim missing citations |
| `CHAPTER_FN_CHAPTER_ORDER_DUPLICATE` | duplicate order_index |

## 3. Per-chapter empty labels

A chapter may have `primary_function=null` and `secondary_functions=[]` **only** when:

- label `empty` or `unknown` is explicitly set as primary, **or**  
- chapter_mode empty path with citations supporting emptiness, **or**  
- listed in limitations with fail-soft policy after repair attempt  

Inventing functions without evidence：FORBIDDEN.

## 4. Outcome mapping

| Outcome | Freeze |
|---|---|
| Legal insufficient | unit/stage **completed**；payload insufficient + empty chapters |
| Illegal after repair | **failed**；no confirmed assets |
| Cancel | no further units |
| Confirmed assets | never silent overwrite（WB-1.10） |

## 5. Prohibited

1. Invent labels to fill non-empty when insufficient  
2. Fuzzy evidence  
3. Fill from chapter-analysis / journey / aggregate  
4. Per-novel keyword gates  
5. Using Pro Insights distribution as empty filler  
