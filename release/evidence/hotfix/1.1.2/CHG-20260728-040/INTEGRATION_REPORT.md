# INTEGRATION_REPORT — CHG-20260728-040

## Status

**INTEGRATED** into `hotfix/1.1.2` (Public + Private)

## Heads

| Role | SHA |
|------|-----|
| Public Integration Start | `a2b48fcd93966615ce086e48064dabad96e4d724` |
| Public MERGE_HEAD (verified issue) | `956afe025c109cdce4a4c46ecadb36660bd94010` |
| Public Merge Commit | `49b4430ca5abfffae01a739f320c5ed83433b9e0` |
| Public Integration Final | `49b4430ca5abfffae01a739f320c5ed83433b9e0` |
| Private Integration Start | `30d8dad8cd649e832999874f7bf16cc1661cf221` |
| Private Verified Issue | `ebb7a8d30464558b1a7488abba8cb88e47700044` |
| Private Merge Commit | `23a0b025db51acaa8e62f4e81bc7628f19a8e2a6` |
| Private Integration Final | `23a0b025db51acaa8e62f4e81bc7628f19a8e2a6` |

## Conflict

- File: `release/changes/CHG-20260728-040.json`
- Type: add/add
- Resolution: semantic merge (see `REGISTRY_CONFLICT_RESOLUTION.md`)
- INFORMATION LOSS: NO

## Content audit

- CHG-041 audit commit `2c317926…` **not** included (MERGE_HEAD fixed at `956afe0`)
- No Whole-Book / VERSION / migration / installer / build artifacts
- Unrelated content: 0

## Tests (this round)

- Public pytest CHG-040 + structured/scene suites: PASS (46)
- Extra reservation/usage suites: PASS (47 passed, 11 skipped)
- Private pytest CHG-040: PASS (1)
- Vitest TasksPage.chg040: PASS (3)
- TypeScript typecheck: PASS
- Registry JSON parse + required-schema (extended status): PASS
- git diff --check (Public/Private): PASS

## Provider / DB

- Real provider calls this round: **0**
- Historical L3 real calls: **2** (aliyun_qwen_plus / qwen3.7-plus, ¥0.02787)
- Formal database writes: **0**
- Database migration: NO

## Release state

- Change status: integrated
- Release pool: included
- Release train: open
- Forward port: pending → `integration/whole-book-v120`

## CHG-041 audit commit handling

- CHG-041 AUDIT COMMIT: `2c31792620f737bad18442548aa592047159af41`
- CHG-041 AUDIT FORWARD ACTION: pending cherry-pick into future CHG-041 issue branch
- Not merged / not deleted / not rewritten this round
