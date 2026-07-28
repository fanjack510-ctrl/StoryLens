# WB-0.2 Whole-Book Data Contracts V1 — Evidence Pack

**STEP:** WB-0.2-DATA-CONTRACTS  
**CHANGE:** CHG-20260728-003  
**MANUAL GATE:** MG-WB-0.2  
**Contract:** `whole_book_contract_v1`  
**Acceptance:** L1 (zero-cost structure)

## Contents

| File | Purpose |
|---|---|
| `BASELINE.json` | Worktree / HEAD baseline for this Step |
| `CONTRACT_MANIFEST.json` | Schema manifest + heads + hashes |
| `PUBLIC_CONTRACT_SCHEMA.json` | Public wire JSON Schema |
| `PRIVATE_CONTRACT_SCHEMA.json` | Private wire JSON Schema |
| `SCHEMA_IDENTITY.json` | Public/Private SHA identity |
| `PUBLIC_ONLY_PERSISTENCE_SCHEMA.json` | Stage/Checkpoint (excluded from identity hash) |
| `CONTRACT_OBJECTS.md` | Per-object field catalog |
| `ENUMS.md` | Frozen enums |
| `V1_PERSISTENCE_MAPPING.md` | Contract ↔ existing ORM mapping |
| `INVARIANTS.md` | Non-negotiable invariants |
| `LEGACY_ADAPTER_REPORT.md` | Legacy overview adapter behavior |
| `TEST_RESULTS.md` | Automated test evidence |
| `MANUAL_GATE.md` | MG-WB-0.2 checklist |
| `FINAL_REPORT.md` | Step completion report |

## Boundaries (this Step)

- No Migration
- No formal DB writes
- No real Provider calls
- No product entry enablement
- No WB-0.3 start
