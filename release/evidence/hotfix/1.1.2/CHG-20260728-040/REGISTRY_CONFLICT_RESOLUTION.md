# REGISTRY_CONFLICT_RESOLUTION — CHG-20260728-040

## Conflict

- File: 
elease/changes/CHG-20260728-040.json
- Type: add/add
- HEAD (ours / hotfix integration): 2b48fcd93966615ce086e48064dabad96e4d724
- MERGE_HEAD (theirs / verified issue): 956afe025c109cdce4a4c46ecadb36660bd94010
- Resolution: semantic merge (not ours/theirs)

## Ours fields (summary)

`json
{
  "status": "investigated",
  "title": "Investigate Aliyun Qwen scene-pipeline structured_output truncation (adjudication max_tokens=768)",
  "release_pool_status": "pending",
  "manual_gate": "REVIEW before IMPLEMENTATION prompt",
  "commits": [
    "03c9fc488ffb76594bc50e46549433f29091ddc0"
  ],
  "acceptance_criteria_count": 5,
  "verification_evidence_count": 3,
  "affected_modules_count": 6,
  "modules_count": 6,
  "created_at": "2026-07-28T06:40:00Z",
  "updated_at": "2026-07-28T07:42:00Z",
  "forward_port_required": true,
  "forward_port_target": "integration/whole-book-v120",
  "public_branch": "fix/1.1.2-structured-output-truncation",
  "private_branch": "fix/1.1.2-structured-output-truncation",
  "base_version": "1.1.1",
  "target_version": "1.1.2",
  "issue_id": "INC-20260728-002"
}
`

## Theirs fields (summary)

`json
{
  "status": "verified",
  "title": "Fix scene_boundary_adjudication structured output truncation (batching + adaptive output budget)",
  "release_pool_status": "pending",
  "manual_gate": "passed_l3_real_provider",
  "commits": [
    "b7d05e73c33b450321d6e39b1b009c1ae16a5d92",
    "dfeec5f74da82fa76875a36933c955ae33a49f4f",
    "90fb771be894c8cd5b72ad17058281482a6e06f0"
  ],
  "acceptance_criteria_count": 8,
  "verification_evidence_count": 10,
  "affected_modules_count": 8,
  "modules_count": 4,
  "created_at": "2026-07-28T06:40:00Z",
  "updated_at": "2026-07-28T07:30:15Z",
  "forward_port_required": true,
  "forward_port_target": "integration/whole-book-v120",
  "public_branch": "fix/1.1.2-structured-output-truncation",
  "private_branch": "fix/1.1.2-structured-output-truncation",
  "base_version": "1.1.1",
  "target_version": "1.1.2",
  "issue_id": "INC-20260728-002"
}
`

## Final fields (summary)

`json
{
  "status": "verified",
  "title": "Fix scene_boundary_adjudication structured output truncation (batching + adaptive output budget)",
  "release_pool_status": "pending",
  "manual_gate": "passed_l3_real_provider",
  "commits": [
    "03c9fc488ffb76594bc50e46549433f29091ddc0",
    "b7d05e73c33b450321d6e39b1b009c1ae16a5d92",
    "dfeec5f74da82fa76875a36933c955ae33a49f4f",
    "90fb771be894c8cd5b72ad17058281482a6e06f0"
  ],
  "acceptance_criteria_count": 13,
  "verification_evidence_count": 14,
  "affected_modules_count": 11,
  "modules_count": 9,
  "created_at": "2026-07-28T06:40:00Z",
  "updated_at": "2026-07-28T08:39:13Z",
  "forward_port_required": true,
  "forward_port_target": "integration/whole-book-v120",
  "public_branch": "fix/1.1.2-structured-output-truncation",
  "private_branch": "fix/1.1.2-structured-output-truncation",
  "base_version": "1.1.1",
  "target_version": "1.1.2",
  "issue_id": "INC-20260728-002"
}
`

## Merge rules applied

| Field | Source |
|-------|--------|
| change id / issue_id / versions / branches | common (identical) |
| title / user_summary / release_impact / manual_gate | theirs (fix-era) |
| status (pre-finalize) | theirs=erified (supersedes ours=investigated) |
| release_pool_status | pending (integration SHA filled in later finalize commit) |
| commits | union (investigation + implementation) |
| acceptance_criteria | union |
| tests | union |
| verification_evidence | union (investigation + implementation + L3) |
| affected_modules | union |
| modules | union |
| files | ours (retains trains/1.1.2.json) |
| technical_summary | theirs + explicit verified heads + null integration commits + integration_real_provider_calls=0 |
| data_compatibility | theirs notes + historical L3=2 / this round=0 |
| created_at | ours |
| updated_at | merge-resolution timestamp |
| forward_port_* | retained pending |
| public_integration_commit / private_integration_commit | null / deferred (not forged) |

## Discarded fields

| Field | Reason |
|-------|--------|
| status=investigated (ours) | superseded by verified implementation+L3 state |
| investigation-only title/user_summary (ours) | replaced by fix-era wording; investigation evidence paths retained |
| investigation-only release_impact (requires_restart=false) | superseded by fix-era restart/updater impact |
| manual_gate investigation text (ours) | superseded by passed_l3_real_provider |

## Information loss

INFORMATION LOSS: NO

All non-conflicting valid data from both sides retained via unions (commits, criteria, tests, evidence, modules). Conflicting scalar fields chose the later verified/fix-era values with reasons above.

## Notes

- CHG-041 audit commit 2c31792620f737bad18442548aa592047159af41 is NOT in MERGE_HEAD and is NOT included.
- Schema status enum on mainline does not list hotfix-extended values (investigated); hotfix train already used them; pre-finalize keeps erified.
