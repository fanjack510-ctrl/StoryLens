# Contract Amendment — STEP 2.3-I0 Adapter Parity

**Change:** CHG-20260725-003
**Step:** STEP-2.3-I0
**Amends:** Runtime engine loading / Fake payload policy (not STEP 2.1 DTO wire shapes)

## Changes

1. Introduced unified `WholeBookOverviewEngineAdapter` Protocol (`analyze_window` / `synthesize_overview`) and optional `ProviderTransport`.
2. Introduced Engine Loader for:
   - `fixture-native-overview-v1`
   - `private-native-overview-v1`
3. Removed Public divergent `FakeFixtureAdapter` payload. Fixture behavior is Canonical Private `fixture_adapter` only; no silent Fake fallback.
4. Loader never silent-downgrades formal engine → Fixture.
5. Ending candidate **asset_type** wire value aligned to Public `AssetType.CONSEQUENCE` (`consequence`). Projection field remains `ending_state`.
6. Fixture `combined_sha256` **unchanged**.

## Impact

- Public: Orchestrator loads engines via Loader; tests must have Private on PYTHONPATH for fixture engine.
- Private: Fixture Adapter emits `consequence` for ending assets.
- Frontend: none for I0.
- Compatibility: walking-skeleton flows continue with `engine_id=fixture-native-overview-v1`.
