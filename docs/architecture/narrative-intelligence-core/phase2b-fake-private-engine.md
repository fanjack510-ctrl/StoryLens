# Phase 2B Fake Private Engine

`FakePrivateWholeBookEngine` (`fake.signed.private_engine`).

## Properties

- `engine_id` contains `fake`/`test`
- `private=false` or `test_private=true` (contract-legal test markers)
- `non_production=true`
- Deterministic synthetic outputs for the first four modules
- Supports cancel / checkpoint / health
- Does not read real novel full text
- Does not produce real analysis conclusions
- Production Loader rejects load

Forbidden: driving Fake outputs from user novel body.
