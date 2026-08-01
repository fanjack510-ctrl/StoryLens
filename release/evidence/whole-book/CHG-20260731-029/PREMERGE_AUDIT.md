# CHG-20260731-029 Pre-merge Audit

## Public
- WAVE D BASE: e35bc99f4fc5327a585c7a5a757c55a9d3723244
- V1.1.2 TAG: v1.1.2 -> 30fe4b6d324ced7f1b0f2792ef60b402f6c157e1 (MATCH expected product source)
- EXPECTED PUBLIC FINAL 8bd06f8 is descendant of tag (docs/build metadata after tag); merge uses tag v1.1.2
- MERGE BASE: 38c85ab4eda0eaa03bd6a7bf8fda7d8deb11a5db
- Wave D unique commits: 45
- v1.1.2 unique commits: 216
- Path intersection potential conflicts (pre-merge heuristic): 4
  - apps/api/app/db/models.py
  - apps/api/app/main.py
  - apps/desktop/src/pages/BookRoutePage.tsx
  - release/unreleased.json
- Dual implementation risk: Wave D adds Free whole-book product surfaces; v1.1.2 adds Journey/scene control fixes — must keep both, not overwrite pages wholesale
- CHG-020/022: not in v1.1.2-only commit list vs Wave D tip; CHG-021 release docs appear on Wave D-only side already — merge of v1.1.2 tag does not newly introduce CHG-020/022 product features beyond shared history

## Private
- WAVE D BASE: 8dc389746880d203d9f2a21dbf5e20515d508764
- V1.1.2 PRIVATE HEAD: 23a0b025db51acaa8e62f4e81bc7628f19a8e2a6
- MERGE BASE: 30d8dad8cd649e832999874f7bf16cc1661cf221
- Wave D unique: 3 (overview/window/contract engines)
- v1.1.2 unique: 2 (boundary adjudication batching hotfix)
- PRIVATE MERGE REQUIRED: YES (scene_boundary hotfix not in Wave D private tip)
