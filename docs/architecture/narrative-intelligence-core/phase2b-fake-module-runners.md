# Phase 2B Fake Module Runners

Classes: `FakeBookOverviewRunner` · `FakeStructureStagesRunner` · `FakeChapterFunctionsRunner` · `FakeStorylinesRunner`

## Allowed outputs

- Legal empty DTO
- Fixed synthetic fixture via `provider_policy.synthetic_fixture_id` / `synthetic_output`
- Explicitly supplied synthetic envelopes

## Forbidden

- Infer conclusions from novel body
- Keyword/title/author protagonist detection
- Chapter-length structure inference
- Character-name storyline detection
- Claiming Fake output is real analysis

All envelopes carry `fake=true`, `synthetic=true`, `non_production=true`.
