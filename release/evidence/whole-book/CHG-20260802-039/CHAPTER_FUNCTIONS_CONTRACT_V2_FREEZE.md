# CHAPTER_FUNCTIONS_CONTRACT_V2_FREEZE

## Decision

```
CANONICAL CONTRACT：V2
CONTRACT ID：ChapterFunctionsResultV2
CONTRACT VERSION：2.0.0
WIRE contract_version：v2
evidence_contract_version：v2
V1 ChapterFunctionsResultDto：adapter-only（Lab / prototypes）
Pro ChapterFunctionsResultV1：FORBIDDEN as Free SoT
```

Desktop Lab DTO is **not** Free product SoT.  
Free API returns **V2** only（or thin view-model mapped from V2）.

## Top-level

| Field | Type | Required | Notes |
|---|---|---|---|
| `contract_version` | string | yes | `"v2"` |
| `evidence_contract_version` | string | yes | `"v2"` |
| `coverage_scope` | string | yes | `local`\|`partial_span`\|`full_selected_range`\|`insufficient` |
| `chapters` | array | yes | may be `[]` only under empty policy |
| `analysis_confidence` | number\|null | no | optional |
| `overall_confidence` | number\|null | no | optional |
| `limitations` | string[] | no | default `[]` |
| `context_capabilities` | object | no | server echo |
| `empty_reason` | string\|null | no | when insufficient / empty binding |

## Chapter item

| Field | Type | Required | Notes |
|---|---|---|---|
| `chapter_id` | string\|int | yes | stable book chapter id |
| `chapter_order` | int | yes | narrative order |
| `primary_function` | string\|null | yes | controlled label or null |
| `secondary_functions` | string[] | yes | 0..N controlled；no primary dup |
| `observed_summary` | claim object | yes* | status+value+citation_ids when observed/inferred |
| `inferred_effect` | claim object\|null | no | optional inferred claim |
| `confidence` | number | yes | 0..1 |
| `supporting_citation_ids` | string[] | yes | catalog-bound；≥1 when any claim observed/inferred |
| `limitations` | string[] | no | per-chapter |

\* When `primary_function` and `secondary_functions` are both empty **and** mode is legal empty/insufficient path, claims may be absent with empty_reason.

### Claim object（align Structure V2）

```
{ "value": string|null, "status": "observed"|"inferred"|"not_observed",
  "citation_ids": string[], "confidence": number|null }
```

## Provenance

Persisted via Narrative Asset `chapter_function` + Run/Snapshot revision binding（Public）.  
Wire may omit heavy provenance； product envelope includes `source_revision` / `run_id` at API layer.

## Forbidden

- Free product returning Lab V1 list SoT  
- Pro Insights distribution payload as Free result  
- Non-catalog citations / fuzzy evidence  
- Markdown fences / wrapper envelopes as provider SoT  
