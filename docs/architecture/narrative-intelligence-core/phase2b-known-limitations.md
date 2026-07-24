# Phase 2B Known Limitations

**Change:** CHG-20260723-040 (post-integration)

1. **Fake runtime only** — `PrivateWholeBookAnalysisRuntime` is synthetic/non-production; `production=True` forbidden. No production default singleton.

2. **No formal prompts / real models** — `FakePromptPackServiceManifest` and `FakeProviderAdapter` only; `formal_prompt=False`, `model_called=False`, `network=False` on pipeline DTO.

3. **No ORM candidate writes** — `RecordingCandidatePersistenceSink` records commands; `orm_written=False` always. Phase 1B persistence wiring deferred.

4. **First four modules only** — `WholeBookModuleSpecRegistry` covers `book_overview`, `structure_stages`, `chapter_functions`, `storylines`. Remaining modules not wired.

5. **Enhanced Scene ORM gap** — Enhanced degrade tested via `FixtureAuxiliaryContextSource`; Scene ORM E2E not covered.

6. **Paragraph grouping defaults are initial** — `max=40`, `overlap=2` not locked by evaluation; `defaults_are_initial_only` in grouping dict.

7. **In-memory context cache** — `InMemoryContextBundleCache` is process-local; not durable across restart.

8. **Formal Run still disabled** — `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`; Integration does not register production whole-book run API.

9. **Production gates unchanged** — `PRO_CAPABILITIES_SHIPPED=false`, `PRODUCTION_DEFAULT_ENGINE_ID=None`, `WHOLE_BOOK_MOCK_LAB_ENABLED=false`.

10. **No migrations** — no new tables; E2E uses existing Phase 1P schema only.

11. **Agent worktrees untouched** — cherry-pick integration only; no merge of agent branches.

12. **Status cap** — CHG-040 and agents 037–039 remain at `tested` max; not `verified` / `ready` / `released` without manual acceptance beyond automated tests.

## Phase 2C+ inputs

- Production engine registration separate from Fake composition root
- Real Provider + formal prompt pack behind capability gates
- Durable candidate persistence via Phase 1B services
- Scene ORM auxiliary source for Enhanced mode
- Remaining module keys beyond first four
- Formal whole-book Run create when product gates allow
