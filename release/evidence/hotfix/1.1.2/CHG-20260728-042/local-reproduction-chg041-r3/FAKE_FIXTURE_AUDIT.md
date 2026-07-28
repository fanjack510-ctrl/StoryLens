# FAKE FIXTURE AUDIT — CHG-042

## MANUAL_GATE_FAKE_FIXTURE

**MISCONFIGURED** (intended `SUCCESS_CAPABLE`, behaves as deterministic failure for multi-scene Journey batches)

## Checks

| Question | Finding |
|----------|---------|
| Designed as success fixture? | Yes (`STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`, fail-inject off). |
| Returns empty profiles? | No for initial batch; returns profiles with wrong shared evidence. |
| Reuses CHG-042 fault fixture? | Not a named fault fixture; production Smoke Fake path. |
| Deliberately simulates repair failure? | No (`SMOKE_FAKE_FAIL=0`). |
| Supports 4-scene full Journey? | **Not in practice** for batched v2 validation. |
| Wrong Fake branch in background? | No — `request_id=smoke-fake-aliyun_qwen_plus` on all 6 invocations. |

## Defect in Fake synthesizer

`chapter_analysis_smoke_fake_transport.synthesize_chapter_smoke_fake_text`:

- Builds one `chunk = paragraph_ids[:2]` from the whole prompt.
- Reuses that chunk as `evidence_paragraph_ids` for **every** scene profile.
- Scene N≠1 then fails `JOURNEY_EVIDENCE_OUT_OF_SCENE`.
- Structural repair prompts then often parse down to incomplete scene_id sets
  (frozen: `got [1]`).

## Gate implication

This Manual Gate environment is **not valid** for product PASS of Reader Journey
completion. Routing/Confirm+Start can pass while Journey Fake inevitably fails.

MANUAL GATE ENVIRONMENT VALID：**NO**
