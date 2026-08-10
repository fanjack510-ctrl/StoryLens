# CHG-071 failure forensics

## EARLIEST FAILURE

- Failed unit: monolithic `WholeBookAnalysisV2` synthesis (all modules in one provider output).
- Configured `max_output_tokens`: **8000**, recovered from `provider_engine.cpython-312.pyc` instruction stream.
- Failure boundary: provider text -> `extract_json_object` -> `json.loads` / Pydantic validation.
- Failure class: **TRUNCATED_JSON / INVALID_JSON** before a formal `WholeBookAnalysisV2` could be materialized.
- Failed calls: **2**; repair calls: **1**; duplicate calls/units: **0/0**; formal user DB writes: **0**.
- Repair failure: repair still operated on the complete giant V2 schema/output, so it retained the same output-size and parse-risk boundary instead of isolating the failed section.

The original console response was not persisted before the prior Codex process exited. Therefore exact `finish_reason`, `prompt_tokens`, `completion_tokens`, and raw response byte/character length are **not recoverable from disk** and are deliberately not fabricated. The acceptance script wrote its report only after successful Pydantic validation, so its output directory is empty. The surviving compiled adapter proves the configured limit and monolithic parse path.

## CASCADE FAILURES

Because no formal result object existed, downstream checks necessarily failed: content richness, evidence, progress completion, formal V2 result, and formal V2 UI. These are consequences, not the earliest provider failure.
