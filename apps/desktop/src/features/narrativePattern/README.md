# Narrative Pattern Map (Agent C / Phase 0B)

Isolated frontend Contract drafts and a visualization spike for **Narrative Structure Map**.

## Scope

- DTO draft types under `contracts/`
- Mock JSON under `mocks/`
- Dependency-free SVG tree prototype under `prototype/`
- **Not** wired to product routes, Pro pages, Capability flags, or API

## Key files

| Path | Purpose |
|------|---------|
| `contracts/patternMap.draft.ts` | Frozen frontend DTO shapes |
| `contracts/patternMap.guards.ts` | Runtime validation for mock / tests |
| `mocks/pattern-map.mock.json` | 3–4 layer fictional sample (~36 default / ~80 expanded) |
| `prototype/PatternMapPrototype.tsx` | Isolated tech spike |
| `lib/evidenceDeepLink.ts` | Evidence → chapter/scene/paragraph deep-link helper |

## Docs

See `docs/architecture/narrative-intelligence-core/`:

- `phase0b-pattern-map-readiness.md`
- `phase1d-pattern-map-contract-draft.md`
- `phase1d-pattern-map-technology-options.md`
- `phase1d-pattern-map-performance.md`

## Run directed tests

```bash
cd apps/desktop
npm run typecheck
npx vitest run src/features/narrativePattern
```
