# PIPELINE_ALIGNMENT — CHG-20260803-042

Order: synthesize_overview → synthesize_structure_stages → synthesize_chapter_functions → project_result → finalize

- Structure = optional derived context
- max_chapters_per_batch = 8
- Provider unit: chapter_functions (_initial / _contract_repair)
- Pause/Resume/Cancel reuse whole-book run machine
- Duplicate resume provider calls = 0 (WB22 tests)
