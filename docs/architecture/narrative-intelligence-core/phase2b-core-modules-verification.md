# Phase 2B Core Modules Verification (CHG-039)

## Directed test command

```powershell
$env:PYTHONPATH = "D:\Dstorylens-wt-narrative-core-modules\apps\api"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest apps/api/tests/test_narrative_phase2b_core_modules.py -q --tb=line --noconftest
```

(Use a Python interpreter with working `_ssl` if system Python 3.11 SSL is broken.)

## Coverage map (tests 01–54+)

Registry · duplicate module · stage consistency · compatibility views · base runner · context validation · four Fake runners · synthetic markers · no text inference · Fake Prompt Pack · prompt hash · production reject · provider adapter · no credential · invalid schema/ref · insufficient evidence · cross-book/snapshot · duplicate/conflict · candidate commands · no ORM/canonical · four module contracts · checkpoint/prompt/context mismatch · resume dedupe · evaluation · zh/en/mixed/degraded · metamorphic suite · metrics · no real prompt/model · formal run disabled · version_manager check · change_registry check · git diff --check

## Result (Agent R local)

`59 passed` on Python 3.12 with `--noconftest` / plugin autoload disabled.

## Integration notes

- Agent Q Evidence Validator not merged — uses `EvidenceValidator` Protocol + Fake fixture.
- Agent P Provider Gateway runtime not merged — uses contract `FakeProviderGateway`.
- Integration (CHG-040) wires composition and E2E.
