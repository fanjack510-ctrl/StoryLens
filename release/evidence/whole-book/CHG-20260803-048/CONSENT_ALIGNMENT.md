# CONSENT_ALIGNMENT — CHG-20260803-048

## Assertions (wb221 + directed regressions)
| Item | Status | Evidence |
|---|---|---|
| create-fixture consent legal call | PASS | `test_whole_book_wb221_e2e_stabilization.py` |
| Consent signature keyword-only (`book_id` / `estimate_id` / `snapshot_id`) | PASS | wb221 |
| Revision change invalidates consent | PASS | wb221 |
| Formal create requires consent | PASS | wb221 |
| Provider disabled blocks formal start after consent | PASS | wb221 |

## Notes
- Fixture path auto-creates consent with corrected call signature (Wave 1 fix from CHG-045).
- Consent binding covers revision + estimate validity; snapshot_id in keyword-only signature.

## Verdict
**CONSENT BINDING: PASS** (directed wb221 + regression scope)
